"""MeterCatalog backed by the local SQLite index (through the MeterRepository Protocol)."""

import dataclasses
from collections.abc import Sequence

from app.domain.exceptions import IndexNotReadyError, NotFoundError
from app.domain.models import Meter, PageResult
from app.repositories.interfaces import MeterQuery, MeterRepository
from app.services.interfaces import CatalogHit, FacetField, MeterFilters

_EMPTY = "the local index is empty; a sync is needed"


def to_meter_query(filters: MeterFilters) -> MeterQuery:
    """Turn service filters into the repository's plain-typed query (enums become strings)."""
    values = {f.name: getattr(filters, f.name) for f in dataclasses.fields(filters)}
    values["status"] = tuple(s.value for s in filters.status)
    for name in ("phase", "install_type", "sort"):
        value = values[name]
        values[name] = value.value if value is not None else None
    return MeterQuery(**values)


class IndexedMeterCatalog:
    def __init__(self, meters: MeterRepository) -> None:
        self._meters = meters

    async def _require_index(self) -> None:
        if await self._meters.count() == 0:
            raise IndexNotReadyError(_EMPTY)

    async def search(self, filters: MeterFilters, page: int, page_size: int) -> PageResult[Meter]:
        await self._require_index()
        return await self._meters.search(to_meter_query(filters), page, page_size)

    async def get(self, meter_id: str) -> CatalogHit:
        await self._require_index()
        meter = await self._meters.get(meter_id)
        if meter is None:
            raise NotFoundError(f"meter {meter_id} not found")
        return CatalogHit(meter, "index", await self._meters.get_synced_at(meter_id))

    async def facets(
        self, filters: MeterFilters, fields: Sequence[FacetField]
    ) -> dict[FacetField, dict[str, int]]:
        await self._require_index()
        result: dict[FacetField, dict[str, int]] = {}
        for field in fields:
            default = getattr(MeterFilters(), field.value)  # facet names equal filter names
            own_dropped = dataclasses.replace(filters, **{field.value: default})
            result[field] = await self._meters.facet_counts(
                to_meter_query(own_dropped), field.value
            )
        return result
