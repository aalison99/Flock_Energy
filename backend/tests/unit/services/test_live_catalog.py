from pathlib import Path

import pytest

from app.domain.exceptions import (
    FilterRequiresIndexError,
    IndexNotReadyError,
    NotFoundError,
    ValidationError,
)
from app.domain.models import InstallStatus, PhaseType
from app.portal.fake import FakePortalClient
from app.services.catalogs.live_catalog import LiveMeterCatalog
from app.services.interfaces import FacetField, MeterFilters, MeterSort
from tests.support.portal_emulator import FIXTURES

FIXTURES_DIR: Path = FIXTURES
TOTAL = 403


@pytest.fixture
def portal() -> FakePortalClient:
    return FakePortalClient(FIXTURES_DIR)


@pytest.fixture
def catalog(portal: FakePortalClient) -> LiveMeterCatalog:
    return LiveMeterCatalog(portal)


def pages_fetched(portal: FakePortalClient) -> list[object]:
    return [args[0] for name, args in portal.calls if name == "list_meters"]


@pytest.mark.anyio
async def test_page_size_50_first_page_uses_portal_pages_1_to_3(
    catalog: LiveMeterCatalog, portal: FakePortalClient
) -> None:
    result = await catalog.search(MeterFilters(), 1, 50)
    assert len(result.items) == 50
    assert result.total == TOTAL
    assert pages_fetched(portal) == [1, 2, 3]
    ids = [m.meter_id for m in result.items]
    assert ids == [f"J{100000 + i}" for i in range(50)]


@pytest.mark.anyio
async def test_second_page_of_50_is_items_51_to_100(
    catalog: LiveMeterCatalog, portal: FakePortalClient
) -> None:
    first = await catalog.search(MeterFilters(), 1, 50)
    portal.calls.clear()
    result = await catalog.search(MeterFilters(), 2, 50)
    assert pages_fetched(portal) == [3, 4, 5]
    assert result.items[0] == (await portal.list_meters(3)).items[10]
    assert len(result.items) == 50
    assert not {m.meter_id for m in first.items} & {m.meter_id for m in result.items}


@pytest.mark.anyio
async def test_page_size_200_uses_ten_portal_pages(
    catalog: LiveMeterCatalog, portal: FakePortalClient
) -> None:
    result = await catalog.search(MeterFilters(), 1, 200)
    assert len(result.items) == 200
    assert pages_fetched(portal) == list(range(1, 11))


@pytest.mark.anyio
async def test_last_partial_page(catalog: LiveMeterCatalog, portal: FakePortalClient) -> None:
    result = await catalog.search(MeterFilters(), 3, 200)
    assert len(result.items) == TOTAL - 400
    assert result.total == TOTAL
    assert pages_fetched(portal) == [21]


@pytest.mark.anyio
async def test_past_the_end_is_empty_with_true_total(
    catalog: LiveMeterCatalog, portal: FakePortalClient
) -> None:
    result = await catalog.search(MeterFilters(), 5, 200)
    assert list(result.items) == []
    assert result.total == TOTAL


@pytest.mark.anyio
async def test_only_needed_pages_are_fetched(
    catalog: LiveMeterCatalog, portal: FakePortalClient
) -> None:
    await catalog.search(MeterFilters(), 2, 10)
    assert pages_fetched(portal) == [1]


@pytest.mark.anyio
async def test_q_is_passed_through(catalog: LiveMeterCatalog, portal: FakePortalClient) -> None:
    result = await catalog.search(MeterFilters(q="se33962"), 1, 50)
    assert [m.meter_id for m in result.items] == ["J100000"]
    assert result.total == 1
    assert portal.calls == [("list_meters", (1, "se33962"))]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("filters", "name"),
    [
        (MeterFilters(dt="DT-001"), "dt"),
        (MeterFilters(status=(InstallStatus.FAULTY,)), "status"),
        (MeterFilters(make=("HPL",)), "make"),
        (MeterFilters(phase=PhaseType.THREE), "phase"),
        (MeterFilters(has_geo=False), "has_geo"),
        (MeterFilters(zone="Z-01"), "zone"),
        (MeterFilters(sort=MeterSort.MAKE), "sort"),
        (MeterFilters(q="se", sort=MeterSort.METER_ID_DESC), "sort"),
    ],
)
async def test_a_filter_other_than_q_or_a_non_default_sort_is_rejected(
    catalog: LiveMeterCatalog, portal: FakePortalClient, filters: MeterFilters, name: str
) -> None:
    with pytest.raises(ValidationError) as info:
        await catalog.search(filters, 1, 50)
    assert info.value.message == f"filter '{name}' requires the local index (not built yet)"
    assert isinstance(info.value, FilterRequiresIndexError)
    assert info.value.details == {"filter": name}
    assert portal.calls == []


@pytest.mark.anyio
async def test_q_with_the_default_sort_is_fine(catalog: LiveMeterCatalog) -> None:
    result = await catalog.search(MeterFilters(q="se33962", sort=MeterSort.METER_ID), 1, 50)
    assert result.total == 1


@pytest.mark.anyio
async def test_get_returns_a_portal_hit_and_not_found_propagates(
    catalog: LiveMeterCatalog,
) -> None:
    hit = await catalog.get("J100000")
    assert hit.meter.serial_no == "SE33962"
    assert (hit.source, hit.synced_at) == ("portal", None)
    with pytest.raises(NotFoundError):
        await catalog.get("J999999")


@pytest.mark.anyio
async def test_facets_require_the_index(catalog: LiveMeterCatalog) -> None:
    with pytest.raises(IndexNotReadyError, match="facets require the local index"):
        await catalog.facets(MeterFilters(), [FacetField.STATUS])


@pytest.mark.anyio
@pytest.mark.parametrize("page_size", [1, 3, 7, 19, 20, 21, 33, 40, 50, 199, 200])
async def test_walking_every_page_yields_the_full_list_once(
    portal: FakePortalClient, page_size: int
) -> None:
    catalog = LiveMeterCatalog(portal)
    expected = [m.meter_id for m in await portal.bulk_export()]
    assert len(expected) == TOTAL
    walked: list[str] = []
    page = 1
    while True:
        portal.calls.clear()
        result = await catalog.search(MeterFilters(), page, page_size)
        assert result.total == TOTAL
        if not result.items:
            break
        walked += [m.meter_id for m in result.items]
        start, end = (page - 1) * page_size, min(page * page_size, TOTAL)
        needed = list(range(start // 20 + 1, (end - 1) // 20 + 2))
        assert pages_fetched(portal) == needed
        page += 1
    assert walked == expected
