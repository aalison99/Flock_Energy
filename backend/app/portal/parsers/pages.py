"""Parsers for the two paged list endpoints: meter search and transformers."""

from app.portal import mappers
from app.portal.parsers.base import JsonParser, paged
from app.portal.parsers.registry import PayloadKind


class SearchPageParser(JsonParser):
    kind = PayloadKind.SEARCH_PAGE

    def build(self, body: dict[str, object]) -> object:
        return paged(body, mappers.meter_from_summary)


class DtPageParser(JsonParser):
    kind = PayloadKind.DT_PAGE

    def build(self, body: dict[str, object]) -> object:
        return paged(body, mappers.transformer_from_dict)
