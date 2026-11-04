from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.domain.exceptions import NotFoundError
from app.portal.fake import FakePortalClient
from app.services.catalogs.indexed_catalog import IndexedMeterCatalog
from app.services.catalogs.live_catalog import LiveMeterCatalog
from app.services.interfaces import FacetField, MeterFilters
from app.services.meter_service import MeterService
from app.services.results import Meta
from tests.support.fake_clock import FakeClock
from tests.support.fakes import FakeFreshness, FakeMeterRepository
from tests.support.portal_emulator import FIXTURES

FIXTURES_DIR: Path = FIXTURES
NOW = datetime(2026, 11, 4, 12, tzinfo=UTC)
MAX_AGE = 3600.0
SYNCED = NOW - timedelta(minutes=10)


@pytest.fixture
def portal() -> FakePortalClient:
    return FakePortalClient(FIXTURES_DIR)


@pytest.fixture
def freshness() -> FakeFreshness:
    return FakeFreshness()


@pytest.fixture
def service(portal: FakePortalClient, freshness: FakeFreshness) -> MeterService:
    return MeterService(LiveMeterCatalog(portal), portal, freshness, FakeClock(NOW), MAX_AGE)


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
async def test_failing_detail_never_asks_for_geo(
    portal: FakePortalClient, freshness: FakeFreshness
) -> None:
    service = MeterService(LiveMeterCatalog(portal), portal, freshness, FakeClock(NOW), MAX_AGE)
    with pytest.raises(NotFoundError):
        await service.get_meter("J999999")
    assert [name for name, _ in portal.calls] == ["get_meter"]


@pytest.mark.anyio
async def test_fetched_at_is_the_older_of_detail_and_geo(
    service: MeterService, freshness: FakeFreshness
) -> None:
    old, new = NOW - timedelta(hours=2), NOW - timedelta(minutes=1)
    freshness.set("get_meter", "J100000", fetched_at=new, expires_at=NOW, stale=False)
    freshness.set("get_geo", "J100000", fetched_at=old, expires_at=NOW, stale=False)
    assert (await service.get_meter("J100000")).meta.fetched_at == old


@pytest.fixture
async def indexed_service(portal: FakePortalClient) -> MeterService:
    repo = FakeMeterRepository(await portal.bulk_export(), SYNCED)
    portal.calls.clear()
    return MeterService(IndexedMeterCatalog(repo), portal, FakeFreshness(), FakeClock(NOW), MAX_AGE)


@pytest.mark.anyio
async def test_index_hit_meta_is_synced_at_and_fresh(
    indexed_service: MeterService, portal: FakePortalClient
) -> None:
    result = await indexed_service.get_meter("J100000")
    assert result.meta == Meta("index", SYNCED, False)
    assert result.geo is not None
    assert result.geo.lat == pytest.approx(26.938961)
    assert [name for name, _ in portal.calls] == []  # geo came with the index row


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("age_s", "stale"), [(3599.0, False), (3600.0, False), (3601.0, True), (86400.0, True)]
)
async def test_index_staleness_is_age_over_max_age(
    portal: FakePortalClient, age_s: float, stale: bool
) -> None:
    repo = FakeMeterRepository(await portal.bulk_export(), NOW - timedelta(seconds=age_s))
    service = MeterService(
        IndexedMeterCatalog(repo), portal, FakeFreshness(), FakeClock(NOW), MAX_AGE
    )
    assert (await service.get_meter("J100000")).meta.stale is stale


@pytest.mark.anyio
async def test_index_hit_without_geo_asks_the_portal(portal: FakePortalClient) -> None:
    meters = [replace(m, geo=None) for m in await portal.bulk_export()]
    service = MeterService(
        IndexedMeterCatalog(FakeMeterRepository(meters, SYNCED)),
        portal,
        FakeFreshness(),
        FakeClock(NOW),
        MAX_AGE,
    )
    portal.calls.clear()
    result = await service.get_meter("J100000")
    assert result.geo is not None
    assert [name for name, _ in portal.calls] == ["get_geo"]
    assert result.meta.source == "index"


@pytest.mark.anyio
async def test_facets_delegate_to_the_catalog(indexed_service: MeterService) -> None:
    result = await indexed_service.facets(MeterFilters(), [FacetField.PHASE])
    assert result == {FacetField.PHASE: {"single": 277, "three": 126}}
