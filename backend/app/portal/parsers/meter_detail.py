"""Parser for the SvelteKit route-data meter detail (devalue page node, two detail formats)."""

from app.domain.exceptions import NotFoundError, UpstreamProtocolError
from app.portal import mappers
from app.portal.devalue import decode
from app.portal.errors import SessionExpired
from app.portal.parsers.base import JsonParser
from app.portal.parsers.detail_formats import DetailFormatRegistry, default_detail_formats
from app.portal.parsers.registry import PayloadKind


class MeterDetailParser(JsonParser):
    kind = PayloadKind.METER_DETAIL

    def __init__(self, formats: DetailFormatRegistry | None = None) -> None:
        self._formats = formats or default_detail_formats()

    def check_signals(self, body: dict[str, object]) -> None:
        if body.get("type") == "redirect":
            if body.get("location") == "/login":
                raise SessionExpired("route data redirected to login")
            raise UpstreamProtocolError(f"unexpected redirect to {body.get('location')!r}")
        super().check_signals(body)

    def build(self, body: dict[str, object]) -> object:
        nodes = body["nodes"]
        if not isinstance(nodes, list):
            raise UpstreamProtocolError("nodes is not a list")
        page = nodes[2]
        if not isinstance(page, dict):
            raise UpstreamProtocolError("page node is not an object")
        if page.get("type") == "error":
            if page.get("status") == 404:
                error = page.get("error")
                message = error.get("message") if isinstance(error, dict) else None
                raise NotFoundError(str(message or "Meter not found"))
            raise UpstreamProtocolError(f"page node error status {page.get('status')!r}")
        decoded = decode(page["data"])
        if not isinstance(decoded, dict) or not isinstance(decoded["detail"], dict):
            raise UpstreamProtocolError("decoded page lacks a detail object")
        hierarchy = decoded["hierarchy"]
        if not isinstance(hierarchy, dict):
            raise UpstreamProtocolError("decoded page lacks a hierarchy object")
        fmt, fields = self._formats.resolve(decoded["detail"])
        return mappers.meter_from_detail(fields, hierarchy, fmt.build)
