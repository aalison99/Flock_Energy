from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncConnection

from app.domain.models import Transformer
from app.portal.fake import FakePortalClient
from app.repositories.sqlite._bulk import CHUNK_SIZE
from app.repositories.sqlite.meter_repo import SqliteMeterRepository
from app.repositories.sqlite.reading_repo import SqliteReadingRepository
from app.repositories.sqlite.transformer_repo import SqliteTransformerRepository
from tests.support.portal_emulator import FIXTURES

pytestmark = pytest.mark.anyio
T0 = datetime(2026, 7, 1, tzinfo=UTC)


async def test_meter_delete_missing_removes_others_and_cascades_readings(
    conn: AsyncConnection,
) -> None:
    portal = FakePortalClient(FIXTURES)
    all_meters = await portal.bulk_export()
    by_id = {m.meter_id: m for m in all_meters}
    with_data = [by_id["J100000"], by_id["J100402"]]  # the fixtures hold readings for these
    meters = with_data + [m for m in all_meters if m not in with_data][:3]
    repo = SqliteMeterRepository(conn)
    await repo.upsert_many(meters, T0)
    readings = SqliteReadingRepository(conn)
    for m in meters[:2]:
        await readings.replace_for_meter(m.meter_id, await portal.get_readings(m.meter_id))
    gone = meters[0].meter_id
    assert await readings.list(gone, None, None)
    keep = [m.meter_id for m in meters[1:]]
    assert await repo.delete_missing(keep) == 1
    assert await repo.get(gone) is None
    assert await repo.count() == 4
    assert await readings.list(gone, None, None) == []
    assert await readings.list(meters[1].meter_id, None, None)


async def test_meter_delete_missing_with_empty_keep_deletes_all(conn: AsyncConnection) -> None:
    meters = (await FakePortalClient(FIXTURES).bulk_export())[:3]
    repo = SqliteMeterRepository(conn)
    await repo.upsert_many(meters, T0)
    assert await repo.delete_missing([]) == 3
    assert await repo.count() == 0


async def test_meter_delete_missing_with_nothing_to_delete(conn: AsyncConnection) -> None:
    meters = (await FakePortalClient(FIXTURES).bulk_export())[:3]
    repo = SqliteMeterRepository(conn)
    await repo.upsert_many(meters, T0)
    assert await repo.delete_missing({m.meter_id for m in meters} | {"unknown"}) == 0
    assert await repo.count() == 3


async def test_meter_delete_missing_handles_1500_ids(conn: AsyncConnection) -> None:
    base = (await FakePortalClient(FIXTURES).bulk_export())[0]
    many = [replace(base, meter_id=f"X{i:05d}", serial_no=f"S{i}") for i in range(1800)]
    repo = SqliteMeterRepository(conn)
    await repo.upsert_many(many, T0)
    keep = [m.meter_id for m in many[:1500]]
    assert await repo.delete_missing(keep) == 300
    assert await repo.count() == 1500
    assert await repo.delete_missing(keep) == 0


async def test_transformer_delete_missing_incl_1500_codes(conn: AsyncConnection) -> None:
    items = [Transformer(f"DT-{i:05d}", f"n{i}", None, 100) for i in range(1800)]
    repo = SqliteTransformerRepository(conn)
    await repo.upsert_many(items, T0)
    keep = [t.code for t in items[:1500]]
    assert await repo.delete_missing(keep) == 300
    assert await repo.count() == 1500
    assert await repo.get(items[1700].code) is None
    assert await repo.delete_missing([]) == 1500


async def test_meter_delete_missing_deletes_more_than_999_and_a_chunk(
    conn: AsyncConnection,
) -> None:
    base = (await FakePortalClient(FIXTURES).bulk_export())[0]
    many = [replace(base, meter_id=f"X{i:05d}", serial_no=f"S{i}") for i in range(1800)]
    repo = SqliteMeterRepository(conn)
    await repo.upsert_many(many, T0)
    keep = {m.meter_id for m in many[:100]}
    assert await repo.delete_missing(keep) == 1700
    assert {m.meter_id for m in await repo.list_all()} == keep


async def test_transformer_delete_missing_deletes_more_than_999_and_a_chunk(
    conn: AsyncConnection,
) -> None:
    items = [Transformer(f"DT-{i:05d}", f"n{i}", None, 100) for i in range(1800)]
    repo = SqliteTransformerRepository(conn)
    await repo.upsert_many(items, T0)
    keep = {t.code for t in items[:100]}
    assert await repo.delete_missing(keep) == 1700
    assert {t.code for t in await repo.list_all()} == keep


async def test_delete_missing_never_binds_more_than_a_chunk_of_parameters(
    conn: AsyncConnection,
) -> None:
    # SQLite's variable limit varies by build (999 to 250,000), so assert on what is sent.
    items = [Transformer(f"DT-{i:05d}", f"n{i}", None, 100) for i in range(1800)]
    repo = SqliteTransformerRepository(conn)
    await repo.upsert_many(items, T0)
    sizes: list[int] = []

    def spy(_c: Any, _cur: Any, statement: str, parameters: Any, *_a: Any) -> None:
        if statement.lstrip().upper().startswith("DELETE"):
            sizes.append(len(parameters))

    event.listen(conn.sync_engine, "before_cursor_execute", spy)
    try:
        assert await repo.delete_missing({t.code for t in items[:100]}) == 1700
    finally:
        event.remove(conn.sync_engine, "before_cursor_execute", spy)
    assert sizes
    assert max(sizes) <= CHUNK_SIZE
    assert len(sizes) == 4  # 1,700 ids in chunks of 500
