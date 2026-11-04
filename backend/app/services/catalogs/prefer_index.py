"""Catalog that prefers the local index and falls back to the live portal."""

from collections.abc import Sequence

from app.domain.exceptions import FilterRequiresIndexError, IndexNotReadyError
from app.domain.models import Meter, PageResult
from app.services.interfaces import CatalogHit, FacetField, MeterCatalog, MeterFilters


class PreferIndexCatalog:
    """Asks the indexed catalog first and delegates to the live one while the index is empty.

    If the live catalog cannot serve the request either (it raises FilterRequiresIndexError;
    other validation errors pass through), the caller gets the clearer "index not ready" error.
    """

    def __init__(self, indexed: MeterCatalog, live: MeterCatalog) -> None:
        self._indexed = indexed
        self._live = live

    async def search(self, filters: MeterFilters, page: int, page_size: int) -> PageResult[Meter]:
        try:
            return await self._indexed.search(filters, page, page_size)
        except IndexNotReadyError as not_ready:
            try:
                return await self._live.search(filters, page, page_size)
            except FilterRequiresIndexError:
                raise not_ready from None

    async def get(self, meter_id: str) -> CatalogHit:
        try:
            return await self._indexed.get(meter_id)
        except IndexNotReadyError:
            return await self._live.get(meter_id)

    async def facets(
        self, filters: MeterFilters, fields: Sequence[FacetField]
    ) -> dict[FacetField, dict[str, int]]:
        try:
            return await self._indexed.facets(filters, fields)
        except IndexNotReadyError:
            return await self._live.facets(filters, fields)
