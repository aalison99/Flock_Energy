import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.domain.exceptions import NotFoundError
from app.portal.fake import FakePortalClient
from app.services.catalogs.live_catalog import LiveMeterCatalog
from app.services.interfaces import MeterFilters
from app.services.meter_service import MeterService
from app.services.results import Meta
from tests.support.fake_clock import FakeClock
from tests.support.fakes import FakeFreshness
from tests.support.portal_emulator import FIXTURES

FIXTURES_DIR: Path = FIXTURES
NOW = datetime(2026, 11, 4, 12, tzinfo=UTC)


@pytest.fixture
def portal() -> FakePortalClient:
    return FakePortalClient(FIXTURES_DIR)


@pytest.fixture
def freshness() -> FakeFreshness:
    return FakeFreshness()


@pytest.fixture
def service(portal: FakePortalClient, freshness: FakeFreshness) -> MeterService:
    return MeterService(LiveMeterCatalog(portal), portal, freshness, FakeClock(NOW))


@pytest.mark.anyio
async def test_get_meter_merges_detail_and_geo(service: MeterService) -> None:
    result = await service.get_meter("J100000")
    assert result.meter.meter_id == "J100000"
    assert result.meter.geo is None
    assert result.geo is not None
    assert result.geo.lat == pytest.approx(26.938961)


@pytest.mark.anyio
async def test_not_found_propagates(service: MeterService) -> None:
    with pytest.raises(NotFoundError):
        await service.get_meter("J999999")


@pytest.mark.anyio
async def test_meta_comes_from_freshness(service: MeterService, freshness: FakeFreshness) -> None:
    fetched = NOW - timedelta(minutes=5)
    freshness.set("get_meter", "J100000", fetched_at=fetched, expires_at=NOW, stale=False)
    result = await service.get_meter("J100000")
    assert result.meta == Meta("portal", fetched, False)


@pytest.mark.anyio
async def test_fallback_meta_when_no_freshness(service: MeterService) -> None:
    result = await service.get_meter("J100000")
    assert result.meta == Meta("portal", NOW, False)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("detail_stale", "geo_stale", "expected"),
    [(False, False, False), (True, False, True), (False, True, True), (True, True, True)],
)
async def test_stale_if_either_is_stale(
    service: MeterService,
    freshness: FakeFreshness,
    detail_stale: bool,
    geo_stale: bool,
    expected: bool,
) -> None:
    then = NOW - timedelta(hours=1)
    freshness.set("get_meter", "J100000", fetched_at=then, expires_at=NOW, stale=detail_stale)
    freshness.set("get_geo", "J100000", fetched_at=then, expires_at=NOW, stale=geo_stale)
    assert (await service.get_meter("J100000")).meta.stale is expected


@pytest.mark.anyio
async def test_list_meters_delegates(service: MeterService) -> None:
    result = await service.list_meters(MeterFilters(q="se33962"), 1, 50)
    assert result.total == 1


@pytest.mark.anyio
async def test_failing_detail_cancels_the_geo_sibling(freshness: FakeFreshness) -> None:
    started = asyncio.Event()
    outcome: list[str] = []

    class SlowGeoPortal(FakePortalClient):
        async def get_geo(self, meter_id: str) -> None:
            started.set()
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                outcome.append("cancelled")
                raise

    class FailingCatalog:
        async def get(self, meter_id: str) -> None:
            await started.wait()
            raise NotFoundError("nope")

    portal = SlowGeoPortal(FIXTURES_DIR)
    service = MeterService(FailingCatalog(), portal, freshness, FakeClock(NOW))  # type: ignore[arg-type]
    with pytest.raises(NotFoundError):
        await service.get_meter("J100000")
    assert outcome == ["cancelled"]


@pytest.mark.anyio
async def test_fetched_at_is_the_older_of_detail_and_geo(
    service: MeterService, freshness: FakeFreshness
) -> None:
    old, new = NOW - timedelta(hours=2), NOW - timedelta(minutes=1)
    freshness.set("get_meter", "J100000", fetched_at=new, expires_at=NOW, stale=False)
    freshness.set("get_geo", "J100000", fetched_at=old, expires_at=NOW, stale=False)
    assert (await service.get_meter("J100000")).meta.fetched_at == old
