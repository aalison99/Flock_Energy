"""MeterRepository query methods checked against the brute-force oracle over all fixtures."""

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from app.domain.models import GeoPoint, Meter
from app.portal.fake import FakePortalClient
from app.repositories.interfaces import MeterQuery
from app.repositories.sqlite.meter_repo import SqliteMeterRepository
from tests.support import meter_oracle
from tests.support.portal_emulator import FIXTURES

pytestmark = pytest.mark.anyio
SYNCED = datetime(2026, 7, 1, 8, 30, tzinfo=UTC)

CASES: dict[str, dict[str, Any]] = {
    "none": {},
    "q_id": {"q": "j1003"},
    "q_serial_ci": {"q": "se339"},
    "status_one": {"status": ("faulty",)},
    "status_any_of": {"status": ("faulty", "decommissioned")},
    "make_any_of": {"make": ("HPL", "L&T")},
    "phase": {"phase": "three"},
    "install_type": {"install_type": "ct_operated"},
    "dt": {"dt": "DT-007"},
    "feeder": {"feeder": "F-007"},
    "substation": {"substation": "SS-01"},
    "subdivision": {"subdivision": "SD-01"},
    "division_everywhere": {"division": "D-01"},
    "circle": {"circle": "C-01"},
    "zone": {"zone": "Z-02"},
    "has_geo_true": {"has_geo": True},
    "has_geo_false": {"has_geo": False},
    "combined": {
        "status": ("installed", "faulty"),
        "make": ("Genus", "HPL"),
        "phase": "single",
        "zone": "Z-01",
        "q": "j10",
    },
    "empty_result": {"dt": "DT-007", "make": ("nobody",)},
}


@pytest.fixture
async def all_meters() -> list[Meter]:
    """Fixture meters; every tenth loses its geo so null-geo handling is exercised."""
    meters = await FakePortalClient(FIXTURES).bulk_export()
    return [replace(m, geo=None) if i % 10 == 0 else m for i, m in enumerate(meters)]


@pytest.fixture
async def repo(conn: AsyncConnection, all_meters: list[Meter]) -> SqliteMeterRepository:
    repository = SqliteMeterRepository(conn)
    await repository.upsert_many(all_meters, SYNCED)
    return repository


@pytest.mark.parametrize("case", CASES)
async def test_search_matches_the_oracle(
    repo: SqliteMeterRepository, all_meters: list[Meter], case: str
) -> None:
    query = MeterQuery(**CASES[case])
    expected = meter_oracle.search(all_meters, query)
    page = await repo.search(query, 1, 1000)
    assert page.total == len(expected)
    assert list(page.items) == expected


@pytest.mark.parametrize("sort", ["meter_id", "-meter_id", "make", "status"])
async def test_sorts_with_ties_broken_by_meter_id(
    repo: SqliteMeterRepository, all_meters: list[Meter], sort: str
) -> None:
    query = MeterQuery(sort=sort)
    page = await repo.search(query, 1, 1000)
    assert list(page.items) == meter_oracle.search(all_meters, query)


async def test_paging_slices_and_totals(repo: SqliteMeterRepository) -> None:
    query = MeterQuery(make=("HPL",))
    first = await repo.search(query, 1, 40)
    second = await repo.search(query, 2, 40)
    third = await repo.search(query, 3, 40)
    assert (first.total, second.total, third.total) == (90, 90, 90)
    assert (len(first.items), len(second.items), len(third.items)) == (40, 40, 10)
    ids = [m.meter_id for p in (first, second, third) for m in p.items]
    assert ids == sorted(ids)
    assert len(set(ids)) == 90
    beyond = await repo.search(query, 9, 40)
    assert (list(beyond.items), beyond.total) == ([], 90)


@pytest.mark.parametrize("text", ["%", "_", "\\", "100%", "j_00000"])
async def test_q_wildcards_and_backslash_match_literally(
    conn: AsyncConnection, all_meters: list[Meter], text: str
) -> None:
    odd = [
        replace(all_meters[1], meter_id="J900001", serial_no="A%B"),
        replace(all_meters[2], meter_id="J900002", serial_no="A_B"),
        replace(all_meters[3], meter_id="J900003", serial_no="A\\B"),
        replace(all_meters[4], meter_id="J900004", serial_no="100% sure"),
    ]
    repository = SqliteMeterRepository(conn)
    await repository.upsert_many([*all_meters, *odd], SYNCED)
    query = MeterQuery(q=text)
    expected = meter_oracle.search([*all_meters, *odd], query)
    page = await repository.search(query, 1, 1000)
    assert list(page.items) == expected
    if text in {"%", "_", "\\"}:
        assert 0 < page.total < 10  # not "everything"


@pytest.mark.parametrize("field", ["status", "make", "phase", "install_type", "dt"])
@pytest.mark.parametrize("case", ["none", "combined", "dt", "empty_result", "has_geo_true"])
async def test_facet_counts_match_the_oracle(
    repo: SqliteMeterRepository, all_meters: list[Meter], field: str, case: str
) -> None:
    query = MeterQuery(**CASES[case])
    # The repository counts with the filters it is given; the catalog drops the field's own.
    own_default = () if field in {"status", "make"} else None
    narrowed = replace(query, **{field: own_default})
    expected = meter_oracle.facet(all_meters, query, field)
    assert await repo.facet_counts(narrowed, field) == expected


async def test_facet_values_are_stored_strings_and_zero_counts_omitted(
    repo: SqliteMeterRepository,
) -> None:
    counts = await repo.facet_counts(MeterQuery(dt="DT-007"), "status")
    assert sum(counts.values()) == 13
    assert all(v > 0 for v in counts.values())
    assert set(counts) <= {"installed", "faulty", "decommissioned", "unknown"}


async def test_within_box_inclusive_bounds_and_null_geo_excluded(
    conn: AsyncConnection, all_meters: list[Meter]
) -> None:
    base = all_meters[1]
    edge = [
        replace(base, meter_id="J800001", geo=GeoPoint(10.0, 20.0)),
        replace(base, meter_id="J800002", geo=GeoPoint(11.0, 21.0)),
        replace(base, meter_id="J800003", geo=GeoPoint(10.5, 20.5)),
        replace(base, meter_id="J800004", geo=GeoPoint(11.0001, 20.5)),
        replace(base, meter_id="J800005", geo=None),
    ]
    repository = SqliteMeterRepository(conn)
    await repository.upsert_many(edge, SYNCED)
    found = await repository.within_box(10.0, 20.0, 11.0, 21.0, MeterQuery(), 100)
    assert [m.meter_id for m in found] == ["J800001", "J800002", "J800003"]
    limited = await repository.within_box(10.0, 20.0, 11.0, 21.0, MeterQuery(), 2)
    assert [m.meter_id for m in limited] == ["J800001", "J800002"]


async def test_within_box_applies_filters(
    repo: SqliteMeterRepository, all_meters: list[Meter]
) -> None:
    query = MeterQuery(make=("HPL",))
    found = await repo.within_box(-90, -180, 90, 180, query, 1000)
    expected = [m for m in meter_oracle.search(all_meters, query) if m.geo is not None]
    assert found == expected


async def test_get_synced_at(repo: SqliteMeterRepository) -> None:
    assert await repo.get_synced_at("J100001") == SYNCED
    assert await repo.get_synced_at("J999999") is None


async def test_facets_omit_null_install_type_and_dt(
    conn: AsyncConnection, all_meters: list[Meter]
) -> None:
    nulls = replace(all_meters[1], meter_id="J800009", install_type=None, dt_code=None)
    repository = SqliteMeterRepository(conn)
    await repository.upsert_many([nulls], SYNCED)
    for field in ("install_type", "dt"):
        counts = await repository.facet_counts(MeterQuery(), field)
        assert None not in counts and "None" not in counts
        assert sum(counts.values()) == 0
