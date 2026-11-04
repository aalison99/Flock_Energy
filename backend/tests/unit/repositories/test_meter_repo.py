from dataclasses import replace
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db.tables import meters as meters_table
from app.domain.models import GeoPoint, InstallStatus, Meter, NodeRef
from app.portal.fake import FakePortalClient
from app.repositories.sqlite.meter_repo import SqliteMeterRepository
from tests.support.portal_emulator import FIXTURES

pytestmark = pytest.mark.anyio
T0 = datetime(2026, 7, 1, tzinfo=UTC)
T1 = datetime(2026, 7, 2, tzinfo=UTC)


async def _fixture_meters() -> list[Meter]:
    return await FakePortalClient(FIXTURES).bulk_export()


async def test_all_fixture_meters_round_trip(conn: AsyncConnection) -> None:
    meters = await _fixture_meters()
    repo = SqliteMeterRepository(conn)
    assert await repo.upsert_many(meters, T0) == len(meters) == 403
    assert await repo.count() == 403
    stored = await repo.list_all()
    assert stored == sorted(meters, key=lambda m: m.meter_id)
    for m in meters:
        assert await repo.get(m.meter_id) == m


async def test_get_missing_returns_none(conn: AsyncConnection) -> None:
    assert await SqliteMeterRepository(conn).get("nope") is None


async def test_empty_upsert_and_count(conn: AsyncConnection) -> None:
    repo = SqliteMeterRepository(conn)
    assert await repo.upsert_many([], T0) == 0
    assert await repo.count() == 0
    assert await repo.list_all() == []


async def test_upsert_twice_is_idempotent(conn: AsyncConnection) -> None:
    meters = (await _fixture_meters())[:20]
    repo = SqliteMeterRepository(conn)
    await repo.upsert_many(meters, T0)
    first = (await conn.execute(select(meters_table).order_by(meters_table.c.meter_id))).all()
    await repo.upsert_many(meters, T0)
    second = (await conn.execute(select(meters_table).order_by(meters_table.c.meter_id))).all()
    assert first == second
    assert await repo.count() == 20


async def test_upsert_updates_existing_and_synced_at(conn: AsyncConnection) -> None:
    m = (await _fixture_meters())[0]
    repo = SqliteMeterRepository(conn)
    await repo.upsert_many([m], T0)
    changed = replace(m, install_status=InstallStatus.DECOMMISSIONED, geo=GeoPoint(1.0, 2.0))
    await repo.upsert_many([changed], T1)
    assert await repo.get(m.meter_id) == changed
    synced = (await conn.execute(select(meters_table.c.synced_at))).scalar_one()
    assert synced == T1.isoformat()
    assert await repo.count() == 1


async def test_upsert_over_chunk_size(conn: AsyncConnection) -> None:
    base = (await _fixture_meters())[0]
    many = [replace(base, meter_id=f"X{i:05d}", serial_no=f"S{i}") for i in range(1203)]
    repo = SqliteMeterRepository(conn)
    assert await repo.upsert_many(many, T0) == 1203
    assert await repo.count() == 1203
    count = (await conn.execute(select(func.count()).select_from(meters_table))).scalar_one()
    assert count == 1203
    listed = await repo.list_all()
    assert [m.meter_id for m in listed] == sorted(m.meter_id for m in many)


async def test_batch_with_differing_dt_codes_round_trips(conn: AsyncConnection) -> None:
    base = (await _fixture_meters())[0]
    assert base.hierarchy is not None
    odd = replace(base, meter_id="ODD1", dt_code="OTHER")
    blank = replace(
        base, meter_id="ODD2", dt_code="X", hierarchy=replace(base.hierarchy, dt=NodeRef(None, "n"))
    )
    repo = SqliteMeterRepository(conn)
    assert await repo.upsert_many([base, odd, blank], T0) == 3
    assert await repo.get("ODD1") == odd
    assert await repo.get("ODD2") == blank
