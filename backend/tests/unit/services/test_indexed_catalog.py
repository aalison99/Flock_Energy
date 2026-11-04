from dataclasses import replace
from datetime import UTC, datetime

import pytest

from app.domain.exceptions import IndexNotReadyError, NotFoundError
from app.domain.models import InstallStatus, InstallType, Meter, PhaseType
from app.portal.fake import FakePortalClient
from app.repositories.interfaces import MeterQuery
from app.services.catalogs.indexed_catalog import IndexedMeterCatalog, to_meter_query
from app.services.interfaces import FacetField, MeterFilters, MeterSort
from tests.support import meter_oracle
from tests.support.fakes import FakeMeterRepository
from tests.support.portal_emulator import FIXTURES

pytestmark = pytest.mark.anyio
SYNCED = datetime(2026, 11, 4, 6, tzinfo=UTC)


@pytest.fixture
async def meters() -> list[Meter]:
    return await FakePortalClient(FIXTURES).bulk_export()


@pytest.fixture
def repo(meters: list[Meter]) -> FakeMeterRepository:
    return FakeMeterRepository(meters, SYNCED)


@pytest.fixture
def catalog(repo: FakeMeterRepository) -> IndexedMeterCatalog:
    return IndexedMeterCatalog(repo)


def test_conversion_defaults() -> None:
    assert to_meter_query(MeterFilters()) == MeterQuery()


def test_conversion_maps_every_field_to_plain_types() -> None:
    filters = MeterFilters(
        q="se",
        status=(InstallStatus.FAULTY, InstallStatus.INSTALLED),
        make=("HPL",),
        phase=PhaseType.THREE,
        install_type=InstallType.CT_OPERATED,
        dt="DT-001",
        feeder="F-001",
        substation="SS-01",
        subdivision="SD-01",
        division="D-01",
        circle="C-01",
        zone="Z-01",
        has_geo=False,
        sort=MeterSort.MAKE,
    )
    query = to_meter_query(filters)
    assert query == MeterQuery(
        q="se",
        status=("faulty", "installed"),
        make=("HPL",),
        phase="three",
        install_type="ct_operated",
        dt="DT-001",
        feeder="F-001",
        substation="SS-01",
        subdivision="SD-01",
        division="D-01",
        circle="C-01",
        zone="Z-01",
        has_geo=False,
        sort="make",
    )
    assert type(query.status[0]) is str
    assert type(query.phase) is str


def test_conversion_covers_every_filter_field() -> None:
    import dataclasses

    assert {f.name for f in dataclasses.fields(MeterFilters)} == {
        f.name for f in dataclasses.fields(MeterQuery)
    }


async def test_search_returns_the_repository_page(
    catalog: IndexedMeterCatalog, meters: list[Meter]
) -> None:
    filters = MeterFilters(make=("HPL",), sort=MeterSort.METER_ID_DESC)
    page = await catalog.search(filters, 2, 25)
    expected = meter_oracle.search(meters, to_meter_query(filters))
    assert page.total == 90
    assert list(page.items) == expected[25:50]


async def test_get_returns_an_index_hit(catalog: IndexedMeterCatalog, meters: list[Meter]) -> None:
    hit = await catalog.get("J100000")
    assert hit.meter == meters[0]
    assert hit.source == "index"
    assert hit.synced_at == SYNCED


async def test_get_unknown_is_not_found(catalog: IndexedMeterCatalog) -> None:
    with pytest.raises(NotFoundError):
        await catalog.get("J999999")


async def test_facets_exclude_each_facets_own_filter(
    catalog: IndexedMeterCatalog, repo: FakeMeterRepository, meters: list[Meter]
) -> None:
    filters = MeterFilters(status=(InstallStatus.FAULTY,), make=("HPL",), phase=PhaseType.SINGLE)
    result = await catalog.facets(filters, [FacetField.STATUS, FacetField.MAKE, FacetField.DT])
    query = to_meter_query(filters)
    assert result[FacetField.STATUS] == meter_oracle.facet(meters, query, "status")
    # Status counts still honour make and phase, but not the status filter itself.
    only_hpl_single = [m for m in meters if m.make == "HPL" and m.phase_type is PhaseType.SINGLE]
    assert sum(result[FacetField.STATUS].values()) == len(only_hpl_single)
    assert set(result[FacetField.STATUS]) > {"faulty"}
    assert sum(result[FacetField.MAKE].values()) == sum(
        1
        for m in meters
        if m.install_status is InstallStatus.FAULTY and m.phase_type.value == "single"
    )
    assert set(result) == {FacetField.STATUS, FacetField.MAKE, FacetField.DT}


async def test_facets_ask_the_repository_without_the_own_filter(
    catalog: IndexedMeterCatalog, repo: FakeMeterRepository
) -> None:
    await catalog.facets(MeterFilters(make=("HPL",), dt="DT-001"), [FacetField.MAKE])
    (name, (query, field)) = repo.calls[-1]
    assert (name, field) == ("facet_counts", "make")
    assert query.make == () and query.dt == "DT-001"


async def test_facets_dt_field_clears_the_dt_filter(
    catalog: IndexedMeterCatalog, repo: FakeMeterRepository
) -> None:
    await catalog.facets(MeterFilters(dt="DT-001", phase=PhaseType.THREE), [FacetField.DT])
    (_, (query, _)) = repo.calls[-1]
    assert query.dt is None and query.phase == "three"


@pytest.mark.parametrize("call", ["search", "get", "facets"])
async def test_empty_index_raises_index_not_ready(call: str) -> None:
    catalog = IndexedMeterCatalog(FakeMeterRepository())
    with pytest.raises(IndexNotReadyError, match="local index is empty"):
        if call == "search":
            await catalog.search(MeterFilters(), 1, 10)
        elif call == "get":
            await catalog.get("J100000")
        else:
            await catalog.facets(MeterFilters(), [FacetField.STATUS])


def test_replace_keeps_working_on_filters() -> None:
    assert replace(MeterFilters(), q="x").q == "x"
