"""Meter use cases: listing and the merged detail (nameplate + hierarchy + geo + freshness)."""

import asyncio

from app.core.interfaces import Clock
from app.domain.models import Meter, PageResult
from app.portal.interfaces import FreshnessReader, PortalClient
from app.services.interfaces import MeterCatalog, MeterFilters
from app.services.results import Meta, MeterDetailResult


class MeterService:
    def __init__(
        self,
        catalog: MeterCatalog,
        portal: PortalClient,
        freshness: FreshnessReader,
        clock: Clock,
    ) -> None:
        self._catalog = catalog
        self._portal = portal
        self._freshness = freshness
        self._clock = clock

    async def list_meters(
        self, filters: MeterFilters, page: int, page_size: int
    ) -> PageResult[Meter]:
        return await self._catalog.search(filters, page, page_size)

    async def get_meter(self, meter_id: str) -> MeterDetailResult:
        # TaskGroup cancels the sibling when one call fails; unwrap to the first domain error.
        try:
            async with asyncio.TaskGroup() as group:
                meter_task = group.create_task(self._catalog.get(meter_id))
                geo_task = group.create_task(self._portal.get_geo(meter_id))
        except ExceptionGroup as group_error:
            raise group_error.exceptions[0] from None
        meter, geo = meter_task.result(), geo_task.result()
        # Freshness keys assume the catalog's get is backed by portal.get_meter (live catalog);
        # a local-index catalog (M6) has no entry there, so fetched_at falls back to now().
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
        return MeterDetailResult(meter, geo, Meta("portal", fetched_at, stale))
