"""SQLite implementation of MeterRepository."""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db.tables import meters
from app.domain.models import Meter
from app.repositories.sqlite import mapping
from app.repositories.sqlite._bulk import upsert_rows


class SqliteMeterRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def upsert_many(self, meters_: Sequence[Meter], synced_at: datetime) -> int:
        rows = [mapping.meter_to_row(m, synced_at) for m in meters_]
        return await upsert_rows(self._conn, meters, rows)

    async def get(self, meter_id: str) -> Meter | None:
        result = await self._conn.execute(select(meters).where(meters.c.meter_id == meter_id))
        row = result.mappings().first()
        return mapping.row_to_meter(row) if row else None

    async def count(self) -> int:
        return (await self._conn.execute(select(func.count()).select_from(meters))).scalar_one()

    async def list_all(self) -> list[Meter]:
        result = await self._conn.execute(select(meters).order_by(meters.c.meter_id))
        return [mapping.row_to_meter(r) for r in result.mappings()]
