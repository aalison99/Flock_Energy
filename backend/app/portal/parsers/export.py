"""Parser for the signed bulk export: every meter with hierarchy and geo."""

from app.portal import mappers
from app.portal.parsers.base import JsonParser, meters
from app.portal.parsers.registry import PayloadKind


class ExportParser(JsonParser):
    kind = PayloadKind.EXPORT

    def build(self, body: dict[str, object]) -> object:
        return meters(body["data"], mappers.meter_from_export)
