"""Parser for the meter geo endpoint (string coordinates)."""

from app.domain.exceptions import UpstreamProtocolError
from app.portal import mappers
from app.portal.parsers.base import JsonParser
from app.portal.parsers.registry import PayloadKind


class GeoParser(JsonParser):
    kind = PayloadKind.GEO

    def build(self, body: dict[str, object]) -> object:
        data = body["data"]
        if data is None:
            return None
        if not isinstance(data, dict):
            raise UpstreamProtocolError("data is not an object")
        return mappers.geo_from_strings(data["latitude"], data["longitude"])
