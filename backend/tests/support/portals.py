"""Test doubles built on FakePortalClient: a subset portal and an in-flight request probe."""

import asyncio
from collections.abc import Collection
from pathlib import Path

from app.domain.models import GeoPoint, Meter, Reading
from app.portal.fake import FakePortalClient
from app.portal.interfaces import PortalPage


class SubsetPortal(FakePortalClient):
    """Serves only `keep` meters from every meter listing (the others vanished upstream)."""

    def __init__(self, fixtures_dir: Path, keep: Collection[str]) -> None:
        super().__init__(fixtures_dir)
        self.keep = set(keep)

    async def bulk_export(self) -> list[Meter]:
        return [m for m in await super().bulk_export() if m.meter_id in self.keep]

    async def list_meters(self, page: int, query: str | None = None) -> PortalPage[Meter]:
        # Crawl listing for the subset: reuse the real paging over the reduced list.
        full = [m for m in self._meters if m.meter_id in self.keep]
        size = 20
        window = full[(max(page, 1) - 1) * size : max(page, 1) * size]
        self.calls.append(("list_meters", (page, query)))
        return PortalPage(items=tuple(window), total=len(full), page=page, page_size=size)


class ProbedPortal(FakePortalClient):
    """Counts concurrent per-meter calls (yielding to the loop inside each) to expose overlap."""

    def __init__(self, fixtures_dir: Path) -> None:
        super().__init__(fixtures_dir)
        self.in_flight = 0
        self.max_in_flight = 0

    async def _probe(self) -> None:
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            for _ in range(3):
                await asyncio.sleep(0)
        finally:
            self.in_flight -= 1

    async def get_meter(self, meter_id: str) -> Meter:
        await self._probe()
        return await super().get_meter(meter_id)

    async def get_geo(self, meter_id: str) -> GeoPoint | None:
        await self._probe()
        return await super().get_geo(meter_id)

    async def get_readings(
        self, meter_id: str, start: object = None, end: object = None
    ) -> list[Reading]:
        await self._probe()
        return await super().get_readings(meter_id)
