"""Transformer use cases: the portal's (cached) DT list, meter counts and meters per DT."""

from app.domain.exceptions import IndexNotReadyError, NotFoundError
from app.domain.models import Meter, PageResult, Transformer
from app.portal.interfaces import PortalClient
from app.services.interfaces import FacetField, MeterCatalog, MeterFilters
from app.services.results import TransformerView

_PORTAL_PAGE_SIZE = 20


class TransformerService:
    def __init__(self, portal: PortalClient, catalog: MeterCatalog) -> None:
        self._portal = portal
        self._catalog = catalog

    async def _all(self) -> list[Transformer]:
        found: list[Transformer] = []
        page = 1
        while True:
            result = await self._portal.list_transformers(page)
            found.extend(result.items)
            if len(result.items) < _PORTAL_PAGE_SIZE or len(found) >= result.total:
                return found
            page += 1

    async def _meter_counts(self) -> dict[str, int] | None:
        """Meters per DT from the index; None (not an error) while the index is empty."""
        try:
            facets = await self._catalog.facets(MeterFilters(), [FacetField.DT])
        except IndexNotReadyError:
            return None
        return facets[FacetField.DT]

    async def list_transformers(
        self, feeder: str | None, page: int, page_size: int
    ) -> PageResult[TransformerView]:
        matching = [t for t in await self._all() if feeder is None or t.feeder_code == feeder]
        matching.sort(key=lambda t: t.code)
        start = (page - 1) * page_size
        window = matching[start : start + page_size]
        counts = await self._meter_counts()
        views = [
            TransformerView(t, None if counts is None else counts.get(t.code, 0)) for t in window
        ]
        return PageResult(items=views, total=len(matching))

    async def get_transformer(self, code: str) -> TransformerView:
        for transformer in await self._all():
            if transformer.code == code:
                counts = await self._meter_counts()
                return TransformerView(transformer, None if counts is None else counts.get(code, 0))
        raise NotFoundError(f"transformer {code} not found")

    async def list_meters(self, code: str, page: int, page_size: int) -> PageResult[Meter]:
        """Meters on one DT; NotFoundError when the portal has no such DT."""
        if all(t.code != code for t in await self._all()):
            raise NotFoundError(f"transformer {code} not found")
        return await self._catalog.search(MeterFilters(dt=code), page, page_size)
