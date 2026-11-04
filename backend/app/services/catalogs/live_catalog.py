"""MeterCatalog backed directly by the live portal (serves only `q` and the default sort)."""

import dataclasses
from collections.abc import Sequence

from app.domain.exceptions import FilterRequiresIndexError, IndexNotReadyError
from app.domain.models import Meter, PageResult
from app.portal.interfaces import PortalClient
from app.services.interfaces import CatalogHit, FacetField, MeterFilters

PORTAL_PAGE_SIZE = 20
_SUPPORTED_FILTERS = frozenset({"q"})
_DEFAULTS = MeterFilters()


class LiveMeterCatalog:
    def __init__(self, portal: PortalClient) -> None:
        self._portal = portal

    async def search(self, filters: MeterFilters, page: int, page_size: int) -> PageResult[Meter]:
        for field in dataclasses.fields(filters):
            unsupported = field.name not in _SUPPORTED_FILTERS
            if unsupported and getattr(filters, field.name) != getattr(_DEFAULTS, field.name):
                raise FilterRequiresIndexError(
                    f"filter '{field.name}' requires the local index (not built yet)",
                    details={"filter": field.name},
                )
        start = (page - 1) * page_size
        end = page * page_size
        first_page = start // PORTAL_PAGE_SIZE + 1
        last_page = (end - 1) // PORTAL_PAGE_SIZE + 1
        collected: dict[int, tuple[Meter, ...]] = {}
        total = 0
        for portal_page in range(first_page, last_page + 1):
            fetched = await self._portal.list_meters(portal_page, filters.q)
            total = fetched.total
            collected[portal_page] = fetched.items
            if len(fetched.items) < PORTAL_PAGE_SIZE:
                break  # the last portal page: nothing further to fetch
        items = [meter for number in sorted(collected) for meter in collected[number]]
        offset = (first_page - 1) * PORTAL_PAGE_SIZE
        return PageResult(items=items[start - offset : end - offset], total=total)

    async def get(self, meter_id: str) -> CatalogHit:
        return CatalogHit(await self._portal.get_meter(meter_id), "portal", None)

    async def facets(
        self, filters: MeterFilters, fields: Sequence[FacetField]
    ) -> dict[FacetField, dict[str, int]]:
        raise IndexNotReadyError("facets require the local index")
