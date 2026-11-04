"""Parser for the readings endpoint: string registers to ascending tz-aware Readings."""

import logging
from collections.abc import Mapping

from app.portal import mappers
from app.portal.parsers.base import JsonParser, rows
from app.portal.parsers.registry import PayloadKind

logger = logging.getLogger(__name__)


def _blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _has_blank_register(row: Mapping[str, object]) -> bool:
    return _blank(row.get("kwh")) or _blank(row.get("kvah"))


class EnergyParser(JsonParser):
    kind = PayloadKind.ENERGY

    def build(self, body: dict[str, object]) -> object:
        """A row with a blank kwh or kvah is skipped (it shows up as a gap); others must parse."""
        everything = rows(body["data"])
        usable = [r for r in everything if not _has_blank_register(r)]
        if len(usable) != len(everything):
            logger.warning(
                "energy payload: skipped %d row(s) with blank registers",
                len(everything) - len(usable),
            )
        readings = [mappers.reading_from_dict(r) for r in usable]
        return sorted(readings, key=lambda r: r.at)
