"""The real PortalClient: maps each operation to a portal HTTP request and a parser."""

import json
import logging
import re
from collections.abc import Awaitable, Callable
from datetime import date
from typing import Any, cast
from urllib.parse import quote

import httpx

from app.core.interfaces import Clock
from app.domain.exceptions import UpstreamAuthError, UpstreamProtocolError, ValidationError
from app.domain.models import GeoPoint, Meter, Reading, Transformer
from app.portal.errors import SignatureRejected
from app.portal.interfaces import PortalPage
from app.portal.parsers.registry import ParserRegistry, PayloadKind
from app.portal.session import PortalSession
from app.portal.signer import RequestSigner

logger = logging.getLogger(__name__)

_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
_EXPORT_PATH = "/portal/export"
_EXPORT_QUERY = "page=1"


class HttpPortalClient:
    """Implements PortalClient over a PortalSession; fails fast, retries belong to callers."""

    def __init__(
        self, session: PortalSession, parsers: ParserRegistry, signer: RequestSigner, clock: Clock
    ) -> None:
        self._session = session
        self._parsers = parsers
        self._signer = signer
        self._clock = clock

    def _parse(self, kind: PayloadKind) -> Callable[[httpx.Response], Any]:
        def parse(response: httpx.Response) -> object:
            try:
                return self._parsers.parse(kind, response.content)
            except SignatureRejected:  # only the export is signed; elsewhere this is nonsense
                raise UpstreamProtocolError(
                    f"{kind.name}: unexpected signature rejection"
                ) from None

        return parse

    async def list_meters(self, page: int, query: str | None = None) -> PortalPage[Meter]:
        return await self._session.request(
            "GET",
            "/portal/meters/search",
            params={"q": query or "", "page": str(page)},
            parse=self._parse(PayloadKind.SEARCH_PAGE),
        )

    async def get_meter(self, meter_id: str) -> Meter:
        return await self._session.request(
            "GET",
            f"/meters/{_id(meter_id)}/__data.json",
            parse=self._parse(PayloadKind.METER_DETAIL),
        )

    async def get_geo(self, meter_id: str) -> GeoPoint | None:
        return await self._session.request(
            "GET", f"/portal/meters/{_id(meter_id)}/geo", parse=self._parse(PayloadKind.GEO)
        )

    async def get_readings(
        self, meter_id: str, start: date | None = None, end: date | None = None
    ) -> list[Reading]:
        if start is not None and end is not None and start > end:
            raise ValidationError("start must not be after end")
        params: dict[str, str] = {}
        if start is not None:
            params["from"] = start.isoformat()
        if end is not None:
            params["to"] = end.isoformat()
        return await self._session.request(
            "GET",
            f"/portal/meters/{_id(meter_id)}/energy",
            params=params or None,
            parse=self._parse(PayloadKind.ENERGY),
        )

    async def list_transformers(self, page: int) -> PortalPage[Transformer]:
        return await self._session.request(
            "GET",
            "/portal/dts",
            params={"page": str(page)},
            parse=self._parse(PayloadKind.DT_PAGE),
        )

    async def bulk_export(self) -> list[Meter]:
        """Fetch the signing secret, then the signed export; refetch the secret once if rejected."""
        for _attempt in range(2):
            secret: str = await self._session.request(
                "GET", "/portal/keys", parse=self._parse(PayloadKind.KEYS)
            )
            try:
                return await self._session.request(
                    "GET",
                    _EXPORT_PATH,
                    params={"page": "1"},
                    headers_factory=self._signer_for(secret),
                    parse=self._parse_export,
                )
            except SignatureRejected:
                logger.info("portal export signature rejected")
        raise UpstreamAuthError("export signature rejected")

    def _signer_for(self, secret: str) -> Callable[[], Awaitable[dict[str, str]]]:
        async def headers() -> dict[str, str]:
            timestamp = int(self._clock.now().timestamp())
            return self._signer.sign("GET", _EXPORT_PATH, _EXPORT_QUERY, secret, timestamp)

        return headers

    def _parse_export(self, response: httpx.Response) -> list[Meter]:
        meters = cast(list[Meter], self._parsers.parse(PayloadKind.EXPORT, response.content))
        total = json.loads(response.content).get("total")
        if isinstance(total, int) and total > len(meters):
            logger.warning("portal export returned %d of %d meters", len(meters), total)
        return meters

    async def aclose(self) -> None:
        await self._session.aclose()


def _id(meter_id: str) -> str:
    """Validate a meter id (portal ids look like J100000) and encode it for use in a path."""
    if not _ID_PATTERN.fullmatch(meter_id):
        raise ValidationError("invalid meter id")
    return quote(meter_id, safe="")
