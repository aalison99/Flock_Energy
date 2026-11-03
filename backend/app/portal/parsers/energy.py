"""Parser for the readings endpoint: string registers to ascending tz-aware Readings."""

from app.portal import mappers
from app.portal.parsers.base import JsonParser, rows
from app.portal.parsers.registry import PayloadKind


class EnergyParser(JsonParser):
    kind = PayloadKind.ENERGY

    def build(self, body: dict[str, object]) -> object:
        readings = [mappers.reading_from_dict(r) for r in rows(body["data"])]
        return sorted(readings, key=lambda r: r.at)
