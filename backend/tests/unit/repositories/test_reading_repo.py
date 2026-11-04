from datetime import UTC, date, datetime, timedelta, timezone

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.domain.exceptions import NotFoundError
from app.domain.models import Reading
from app.portal.fake import FakePortalClient
from app.repositories.sqlite.meter_repo import SqliteMeterRepository
from app.repositories.sqlite.reading_repo import SqliteReadingRepository
from tests.support.portal_emulator import FIXTURES

pytestmark = pytest.mark.anyio
IST = timezone(timedelta(hours=5, minutes=30))
T0 = datetime(2026, 7, 1, tzinfo=UTC)


def _r(day: int, hour: int, minute: int = 0, kwh: float = 1.0) -> Reading:
    return Reading(datetime(2026, 6, day, hour, minute, tzinfo=IST), kwh, kwh * 2, 230.0)


@pytest.fixture
async def seeded(conn: AsyncConnection) -> SqliteReadingRepository:
    meters = (await FakePortalClient(FIXTURES).bulk_export())[:2]
    await SqliteMeterRepository(conn).upsert_many(meters, T0)
    return SqliteReadingRepository(conn)


async def _ids(conn: AsyncConnection) -> list[str]:
    rows = await conn.execute(text("SELECT meter_id FROM meters ORDER BY meter_id"))
    return [r[0] for r in rows]


async def test_replace_and_list_round_trip(
    conn: AsyncConnection, seeded: SqliteReadingRepository
) -> None:
    mid = (await _ids(conn))[0]
    rs = [_r(24, 0), _r(23, 23, 30, 5.0), Reading(_r(25, 1).at, 9.5, 19.0, None)]
    assert await seeded.replace_for_meter(mid, rs) == 3
    got = await seeded.list(mid, None, None)
    assert got == sorted(rs, key=lambda r: r.at)
    assert all(g.at.utcoffset() == timedelta(hours=5, minutes=30) for g in got)
    assert await seeded.count() == 3


async def test_replace_replaces_only_that_meter(
    conn: AsyncConnection, seeded: SqliteReadingRepository
) -> None:
    a, b = (await _ids(conn))[:2]
    await seeded.replace_for_meter(a, [_r(24, 0), _r(24, 1)])
    await seeded.replace_for_meter(b, [_r(24, 0)])
    await seeded.replace_for_meter(a, [_r(25, 0)])
    assert [r.at.day for r in await seeded.list(a, None, None)] == [25]
    assert len(await seeded.list(b, None, None)) == 1


async def test_replace_with_empty_clears(
    conn: AsyncConnection, seeded: SqliteReadingRepository
) -> None:
    mid = (await _ids(conn))[0]
    await seeded.replace_for_meter(mid, [_r(24, 0)])
    assert await seeded.replace_for_meter(mid, []) == 0
    assert await seeded.count() == 0


async def test_replace_is_atomic_when_an_insert_fails(
    conn: AsyncConnection, seeded: SqliteReadingRepository
) -> None:
    mid = (await _ids(conn))[0]
    old = [_r(24, 0), _r(24, 1)]
    await seeded.replace_for_meter(mid, old)
    bad = [_r(25, 0), _r(25, 1), _r(25, 2, kwh=float("nan")), _r(25, 3)]
    # a NaN register is stored as NULL, violating NOT NULL mid-batch
    with pytest.raises(IntegrityError):
        await seeded.replace_for_meter(mid, bad)
    assert await seeded.list(mid, None, None) == old


async def test_replace_for_unknown_meter_is_not_found_and_keeps_rows(
    conn: AsyncConnection, seeded: SqliteReadingRepository
) -> None:
    with pytest.raises(NotFoundError, match="meter ghost not in index"):
        await seeded.replace_for_meter("ghost", [_r(24, 0)])
    assert await seeded.count() == 0


async def test_duplicate_instants_keep_the_first(
    conn: AsyncConnection, seeded: SqliteReadingRepository
) -> None:
    mid = (await _ids(conn))[0]
    first = _r(25, 1, kwh=1.0)
    same_instant_utc = Reading(first.at.astimezone(UTC), 99.0, 99.0, None)
    assert await seeded.replace_for_meter(mid, [first, _r(25, 1, kwh=7.0), same_instant_utc]) == 1
    assert await seeded.list(mid, None, None) == [first]


async def test_replace_first_statement_rolls_back_with_caller(
    engine: AsyncEngine,
) -> None:
    async with engine.begin() as c:
        meters = (await FakePortalClient(FIXTURES).bulk_export())[:1]
        await SqliteMeterRepository(c).upsert_many(meters, T0)
        mid = meters[0].meter_id
        await SqliteReadingRepository(c).replace_for_meter(mid, [_r(24, 0)])
    with pytest.raises(RuntimeError):
        async with engine.begin() as c:
            await SqliteReadingRepository(c).replace_for_meter(mid, [_r(25, 0), _r(25, 1)])
            raise RuntimeError("boom")
    async with engine.begin() as c:
        assert await SqliteReadingRepository(c).list(mid, None, None) == [_r(24, 0)]


async def test_range_filter_uses_inclusive_ist_days(
    conn: AsyncConnection, seeded: SqliteReadingRepository
) -> None:
    mid = (await _ids(conn))[0]
    rs = [_r(23, 23, 30), _r(24, 0), _r(24, 23, 30), _r(25, 0)]
    await seeded.replace_for_meter(mid, rs)
    day = await seeded.list(mid, date(2026, 6, 24), date(2026, 6, 24))
    assert day == [rs[1], rs[2]]
    assert await seeded.list(mid, date(2026, 6, 24), None) == rs[1:]
    assert await seeded.list(mid, None, date(2026, 6, 23)) == rs[:1]
    assert await seeded.list(mid, date(2026, 6, 26), None) == []


async def test_list_unknown_meter_is_empty(seeded: SqliteReadingRepository) -> None:
    assert await seeded.list("nope", None, None) == []


async def test_fk_cascade_removes_readings(
    conn: AsyncConnection, seeded: SqliteReadingRepository
) -> None:
    mid = (await _ids(conn))[0]
    await seeded.replace_for_meter(mid, [_r(24, 0)])
    await conn.execute(text("DELETE FROM meters WHERE meter_id = :m"), {"m": mid})
    assert await seeded.count() == 0


async def test_large_batch(conn: AsyncConnection, seeded: SqliteReadingRepository) -> None:
    mid = (await _ids(conn))[0]
    base = datetime(2026, 1, 1, tzinfo=IST)
    rs = [Reading(base + timedelta(minutes=30 * i), float(i), float(i), None) for i in range(1300)]
    assert await seeded.replace_for_meter(mid, rs) == 1300
    assert await seeded.list(mid, None, None) == rs


# --- list_for_meters (M8) ----------------------------------------------------------------------


async def test_list_for_meters_none_means_all_and_groups_ascending(
    conn: AsyncConnection, seeded: SqliteReadingRepository
) -> None:
    a, b = (await _ids(conn))[:2]
    await seeded.replace_for_meter(a, [_r(25, 0), _r(24, 0)])
    await seeded.replace_for_meter(b, [_r(24, 1)])
    got = await seeded.list_for_meters(None, None, None)
    assert set(got) == {a, b}
    assert [r.at.day for r in got[a]] == [24, 25]  # ascending
    assert len(got[b]) == 1


async def test_list_for_meters_subset_and_empty(
    conn: AsyncConnection, seeded: SqliteReadingRepository
) -> None:
    a, b = (await _ids(conn))[:2]
    await seeded.replace_for_meter(a, [_r(24, 0)])
    await seeded.replace_for_meter(b, [_r(24, 1)])
    assert set(await seeded.list_for_meters([b, "J999999"], None, None)) == {b}
    assert await seeded.list_for_meters([], None, None) == {}


async def test_list_for_meters_uses_ist_day_bounds(
    conn: AsyncConnection, seeded: SqliteReadingRepository
) -> None:
    a = (await _ids(conn))[0]
    rs = [
        Reading(datetime(2026, 6, 23, 23, 59, tzinfo=IST), 1, 2, None),  # day before start
        Reading(datetime(2026, 6, 24, 0, 0, tzinfo=IST), 2, 4, None),  # first instant of start
        Reading(datetime(2026, 6, 24, 23, 59, tzinfo=IST), 3, 6, None),  # last minute of end
        Reading(datetime(2026, 6, 25, 0, 0, tzinfo=IST), 4, 8, None),  # day after end
    ]
    await seeded.replace_for_meter(a, rs)
    got = await seeded.list_for_meters([a], date(2026, 6, 24), date(2026, 6, 24))
    assert [r.kwh_register for r in got[a]] == [2, 3]
    only_start = await seeded.list_for_meters([a], date(2026, 6, 25), None)
    assert [r.kwh_register for r in only_start[a]] == [4]


async def test_list_for_meters_chunks_ids_in_batches_of_at_most_500(
    conn: AsyncConnection, seeded: SqliteReadingRepository
) -> None:
    real = await _ids(conn)
    assert len(real) >= 2
    # 600 unknown ids between two real ones: they must land in different chunks.
    ids = [real[0], *[f"J9{n:05d}" for n in range(600)], real[1]]
    await seeded.replace_for_meter(real[0], [_r(24, 0)])
    await seeded.replace_for_meter(real[1], [_r(24, 1)])
    seen: list[int] = []

    def count(_c: object, _cur: object, _stmt: str, params: object, *_a: object) -> None:
        seen.append(len(params))  # type: ignore[arg-type]

    event.listen(conn.sync_connection, "before_cursor_execute", count)
    try:
        got = await seeded.list_for_meters(ids, None, None)
    finally:
        event.remove(conn.sync_connection, "before_cursor_execute", count)
    assert set(got) == {real[0], real[1]}
    assert len(seen) == 2 and max(seen) <= 500
