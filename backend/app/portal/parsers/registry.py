"""Registry mapping a PayloadKind to the parser that decodes that portal response."""

from enum import StrEnum
from typing import Protocol


class PayloadKind(StrEnum):
    SEARCH_PAGE = "search_page"
    DT_PAGE = "dt_page"
    METER_DETAIL = "meter_detail"
    GEO = "geo"
    ENERGY = "energy"
    EXPORT = "export"
    KEYS = "keys"
    LOGIN_ACTION = "login_action"


class PayloadParser(Protocol):
    """Turns raw response bytes into domain objects, raising on embedded signals."""

    kind: PayloadKind

    def parse(self, raw: bytes) -> object: ...


class ParserRegistry:
    """Holds one parser per kind."""

    def __init__(self) -> None:
        self._parsers: dict[PayloadKind, PayloadParser] = {}

    def register(self, parser: PayloadParser) -> None:
        if parser.kind in self._parsers:
            raise ValueError(f"parser already registered for {parser.kind}")
        self._parsers[parser.kind] = parser

    def get(self, kind: PayloadKind) -> PayloadParser:
        return self._parsers[kind]

    def parse(self, kind: PayloadKind, raw: bytes) -> object:
        return self.get(kind).parse(raw)


def default_registry() -> ParserRegistry:
    """A registry holding every built-in parser."""
    from app.portal.parsers.energy import EnergyParser
    from app.portal.parsers.export import ExportParser
    from app.portal.parsers.geo import GeoParser
    from app.portal.parsers.keys import KeysParser
    from app.portal.parsers.login import LoginActionParser
    from app.portal.parsers.meter_detail import MeterDetailParser
    from app.portal.parsers.pages import DtPageParser, SearchPageParser

    registry = ParserRegistry()
    for parser in (
        SearchPageParser(),
        DtPageParser(),
        MeterDetailParser(),
        GeoParser(),
        EnergyParser(),
        ExportParser(),
        KeysParser(),
        LoginActionParser(),
    ):
        registry.register(parser)
    return registry
