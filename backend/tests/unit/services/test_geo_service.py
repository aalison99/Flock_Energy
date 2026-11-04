from dataclasses import replace

import pytest

from app.domain.exceptions import IndexNotReadyError, ValidationError
from app.domain.models import GeoPoint, Meter
from app.portal.fake import FakePortalClient
from app.services.geo import haversine_km
from app.services.geo_service import BBoxResult, GeoService
from app.services.interfaces import MeterFilters
from tests.support.fakes import FakeMeterRepository
from tests.support.portal_emulator import FIXTURES

pytestmark = pytest.mark.anyio
JAIPUR = GeoPoint(26.9124, 75.7873)


@pytest.fixture
async def meters() -> list[Meter]:
    return await FakePortalClient(FIXTURES).bulk_export()


@pytest.fixture
def service(meters: list[Meter]) -> GeoService:
    return GeoService(FakeMeterRepository(meters))


async def test_near_keeps_exactly_the_meters_within_radius_sorted(
    service: GeoService, meters: list[Meter]
) -> None:
    found = await service.near(JAIPUR, 5.0, 500, MeterFilters())
    expected = sorted(
        (
            (m, haversine_km(JAIPUR, m.geo))
            for m in meters
            if m.geo and haversine_km(JAIPUR, m.geo) <= 5.0
        ),
        key=lambda pair: (pair[1], pair[0].meter_id),
    )
    assert expected  # the fixtures do put meters within 5 km
    assert [(m.meter_id, d) for m, d in found] == [(m.meter_id, d) for m, d in expected]
    assert all(d <= 5.0 for _, d in found)


async def test_near_excludes_meters_in_the_box_corner_beyond_the_radius(
    meters: list[Meter],
) -> None:
    base = meters[0]
    inside = replace(base, meter_id="J800001", geo=GeoPoint(JAIPUR.lat + 0.0089, JAIPUR.lng))
    corner = replace(
        base, meter_id="J800002", geo=GeoPoint(JAIPUR.lat + 0.0089, JAIPUR.lng + 0.0099)
    )
    service = GeoService(FakeMeterRepository([inside, corner]))
    found = await service.near(JAIPUR, 1.0, 10, MeterFilters())
    assert [m.meter_id for m, _ in found] == ["J800001"]


async def test_near_includes_a_meter_exactly_at_the_radius(
    meters: list[Meter], monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services import geo_service

    monkeypatch.setattr(geo_service, "haversine_km", lambda a, b: 2.0)
    on_edge = replace(meters[0], meter_id="J800001", geo=GeoPoint(JAIPUR.lat + 0.001, JAIPUR.lng))
    service = GeoService(FakeMeterRepository([on_edge]))
    assert [(m.meter_id, d) for m, d in await service.near(JAIPUR, 2.0, 10, MeterFilters())] == [
        ("J800001", 2.0)
    ]
    assert await service.near(JAIPUR, 1.999, 10, MeterFilters()) == []


async def test_near_ties_break_by_meter_id_and_limit_caps(meters: list[Meter]) -> None:
    base = meters[0]
    twins = [replace(base, meter_id=f"J80000{i}", geo=JAIPUR) for i in (3, 1, 2)]
    service = GeoService(FakeMeterRepository(twins))
    found = await service.near(JAIPUR, 1.0, 2, MeterFilters())
    assert [(m.meter_id, d) for m, d in found] == [("J800001", 0.0), ("J800002", 0.0)]


async def test_near_applies_filters(service: GeoService, meters: list[Meter]) -> None:
    found = await service.near(JAIPUR, 50.0, 500, MeterFilters(make=("HPL",)))
    assert found and {m.make for m, _ in found} == {"HPL"}


async def test_near_on_an_empty_index_is_index_not_ready() -> None:
    with pytest.raises(IndexNotReadyError):
        await GeoService(FakeMeterRepository()).near(JAIPUR, 1.0, 10, MeterFilters())


async def test_bbox_returns_meters_inside_and_flags_truncation(
    service: GeoService, meters: list[Meter]
) -> None:
    everything = await service.within_bbox(-90, -180, 90, 180, MeterFilters(), 1000)
    assert everything == BBoxResult(items=sorted(meters, key=lambda m: m.meter_id), truncated=False)
    exact = await service.within_bbox(-90, -180, 90, 180, MeterFilters(), 403)
    assert (len(exact.items), exact.truncated) == (403, False)
    cut = await service.within_bbox(-90, -180, 90, 180, MeterFilters(), 400)
    assert (len(cut.items), cut.truncated) == (400, True)
    assert [m.meter_id for m in cut.items] == [m.meter_id for m in everything.items[:400]]


async def test_bbox_asks_the_repository_for_one_extra_row(meters: list[Meter]) -> None:
    repo = FakeMeterRepository(meters)
    await GeoService(repo).within_bbox(0, 0, 90, 180, MeterFilters(), 7)
    name, args = repo.calls[-1]
    assert name == "within_box" and args[-1] == 8


@pytest.mark.parametrize(
    "box", [(10, 0, 5, 1), (0, 10, 1, 5)], ids=["min_lat>max_lat", "min_lng>max_lng"]
)
async def test_bbox_inverted_is_validation_error(
    service: GeoService, box: tuple[float, float, float, float]
) -> None:
    with pytest.raises(ValidationError):
        await service.within_bbox(*box, MeterFilters(), 10)


async def test_bbox_degenerate_box_is_allowed(service: GeoService) -> None:
    result = await service.within_bbox(1, 1, 1, 1, MeterFilters(), 10)
    assert result == BBoxResult(items=[], truncated=False)


async def test_bbox_on_an_empty_index_is_index_not_ready() -> None:
    with pytest.raises(IndexNotReadyError):
        await GeoService(FakeMeterRepository()).within_bbox(0, 0, 1, 1, MeterFilters(), 10)
