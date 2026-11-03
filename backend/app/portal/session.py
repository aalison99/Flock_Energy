"""One authenticated HTTP session to the portal: lazy login, expiry replay, error mapping."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

from app.domain.exceptions import (
    UpstreamAuthError,
    UpstreamProtocolError,
    UpstreamUnavailableError,
)
from app.portal.errors import SessionExpired
from app.portal.parsers.registry import PayloadKind, default_registry
from app.portal.secret import Secret

logger = logging.getLogger(__name__)

_PARSE_STATUSES = frozenset({401, 404})  # the body carries the real error signal


@dataclass(frozen=True)
class PortalCredentials:
    email: str
    password: Secret


class PortalSession:
    """Owns the httpx client and cookie jar; logs in on first use and again when it expires."""

    def __init__(
        self,
        base_url: str,
        credentials: PortalCredentials,
        *,
        timeout_s: float,
        transport: httpx.AsyncBaseTransport | None = None,
        user_agent: str = "urja-meter-api/0.1",
    ) -> None:
        if not base_url.startswith("https://"):
            raise ValueError("portal base_url must be https (the session cookie is Secure)")
        self._origin = base_url.rstrip("/")
        self._credentials = credentials
        self._parsers = default_registry()
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout_s,
            follow_redirects=False,
            transport=transport,
            headers={"User-Agent": user_agent, "Accept": "application/json"},
        )
        self._lock = asyncio.Lock()
        self._generation = 0  # 0 = never logged in
        self._closed = False

    def __repr__(self) -> str:
        return f"PortalSession(base_url={self._origin!r}, generation={self._generation})"

    async def request[T](
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        headers_factory: Callable[[], Awaitable[dict[str, str]]] | None = None,
        parse: Callable[[httpx.Response], T],
    ) -> T:
        """Send a request and parse it; on an expired session re-login once and replay."""
        if self._closed:
            raise UpstreamUnavailableError("portal session is closed")
        await self._ensure_login()
        generation = self._generation
        try:
            return await self._attempt(method, path, params, headers_factory, parse)
        except SessionExpired:
            pass
        await self._relogin(generation)
        try:
            return await self._attempt(method, path, params, headers_factory, parse)
        except SessionExpired:
            raise UpstreamAuthError("session could not be re-established") from None

    async def aclose(self) -> None:
        """Best-effort sign-out, then close the client; safe to call repeatedly."""
        if self._closed:
            return
        self._closed = True
        try:
            if self._generation > 0:
                try:
                    await self._client.post("/api/auth/sign-out", headers={"Origin": self._origin})
                except Exception:  # shutdown must never fail
                    logger.debug("portal sign-out failed", exc_info=False)
        finally:
            await self._client.aclose()  # also on cancellation

    async def _ensure_login(self) -> None:
        # A failed first login leaves generation 0, so every request retries it; M3's circuit
        # breaker is what stops us hammering the portal login with a bad password.
        async with self._lock:
            if self._generation == 0:
                await self._login()
                self._generation = 1
                logger.info("portal login ok")

    async def _relogin(self, seen_generation: int) -> None:
        async with self._lock:
            if self._generation != seen_generation:
                return  # someone else already re-logged in; just replay
            await self._login()
            self._generation += 1
            logger.info("portal re-login (generation %d)", self._generation)

    async def _login(self) -> None:
        response = await self._send(
            "POST",
            "/login",
            data={
                "email": self._credentials.email,
                "password": self._credentials.password.reveal(),
            },
            headers={"Origin": self._origin, "x-sveltekit-action": "true"},
        )
        self._raise_for_server_trouble(response)
        if response.status_code != 200:
            raise UpstreamAuthError(f"login rejected: HTTP {response.status_code}")
        self._parsers.parse(PayloadKind.LOGIN_ACTION, response.content)

    async def _attempt[T](
        self,
        method: str,
        path: str,
        params: dict[str, str] | None,
        headers_factory: Callable[[], Awaitable[dict[str, str]]] | None,
        parse: Callable[[httpx.Response], T],
    ) -> T:
        headers = await headers_factory() if headers_factory else None
        response = await self._send(method, path, params=params, headers=headers)
        status = response.status_code
        if status in (302, 303) and urlsplit(response.headers.get("location", "")).path == "/login":
            raise SessionExpired("redirected to login")
        self._raise_for_server_trouble(response)
        if 200 <= status < 300 or status in _PARSE_STATUSES:
            return parse(response)
        raise UpstreamProtocolError(f"unexpected HTTP {status} from portal")

    async def _send(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        data: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        try:
            return await self._client.request(
                method, path, params=params, data=data, headers=headers
            )
        except httpx.TransportError as exc:
            raise UpstreamUnavailableError(f"portal unreachable: {type(exc).__name__}") from None
        except (httpx.HTTPError, httpx.InvalidURL) as exc:  # e.g. DecodingError
            raise UpstreamProtocolError(f"portal response unusable: {type(exc).__name__}") from None

    @staticmethod
    def _raise_for_server_trouble(response: httpx.Response) -> None:
        status = response.status_code
        if status == 429:
            raw = response.headers.get("retry-after", "").strip()
            retry_after = int(raw) if raw.isascii() and raw.isdigit() else None
            raise UpstreamUnavailableError(
                "portal rate limited: HTTP 429", retry_after_s=retry_after
            )
        if status >= 500:
            raise UpstreamUnavailableError(f"portal error: HTTP {status}")
