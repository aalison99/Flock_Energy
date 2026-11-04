"""Meter use cases: listing, facets and the merged detail (nameplate, hierarchy, geo, freshness)."""

from collections.abc import Sequence

from app.core.interfaces import Clock
from app.domain.models import Meter, PageResult
from app.portal.interfaces import FreshnessReader, PortalClient
from app.services.interfaces import CatalogHit, FacetField, MeterCatalog, MeterFilters
from app.services.results import Meta, MeterDetailResult


class MeterService:
    def __init__(
        self,
        catalog: MeterCatalog,
        portal: PortalClient,
        freshness: FreshnessReader,
        clock: Clock,
        index_max_age_s: float,
    ) -> None:
        self._catalog = catalog
        self._portal = portal
        self._freshness = freshness
        self._clock = clock
        self._index_max_age_s = index_max_age_s

    async def list_meters(
        self, filters: MeterFilters, page: int, page_size: int
    ) -> PageResult[Meter]:
        return await self._catalog.search(filters, page, page_size)

    async def facets(
        self, filters: MeterFilters, fields: Sequence[FacetField]
    ) -> dict[FacetField, dict[str, int]]:
        return await self._catalog.facets(filters, fields)

    async def get_meter(self, meter_id: str) -> MeterDetailResult:
        hit = await self._catalog.get(meter_id)
        # The index row carries the position; the live portal needs a second call for it.
        geo = hit.meter.geo
        if geo is None:
            geo = await self._portal.get_geo(meter_id)
        if hit.source == "index":
            return MeterDetailResult(hit.meter, geo, self._index_meta(hit))
        entries = [
            f
            for f in (
                self._freshness.freshness("get_meter", meter_id),
                self._freshness.freshness("get_geo", meter_id),
            )
            if f is not None
        ]
        fetched_at = min((f.fetched_at for f in entries), default=self._clock.now())
        stale = any(f.stale for f in entries)
        return MeterDetailResult(hit.meter, geo, Meta("portal", fetched_at, stale))

    def _index_meta(self, hit: CatalogHit) -> Meta:
        now = self._clock.now()
        synced_at = hit.synced_at or now
        return Meta("index", synced_at, (now - synced_at).total_seconds() > self._index_max_age_s)
