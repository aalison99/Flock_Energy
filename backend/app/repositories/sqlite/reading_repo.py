"""SQLite implementation of ReadingRepository."""

from collections.abc import Sequence
from datetime import date
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db.tables import readings
from app.domain.exceptions import NotFoundError
from app.domain.models import Reading
from app.repositories.sqlite import mapping
from app.repositories.sqlite._bulk import insert_rows


class SqliteReadingRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def replace_for_meter(self, meter_id: str, items: Sequence[Reading]) -> int:
        """Delete then insert inside a savepoint, so a failure keeps the old rows."""
        by_instant: dict[str, dict[str, Any]] = {}
        for r in items:  # one row per instant; the first occurrence wins
            row = mapping.reading_to_row(meter_id, r)
            by_instant.setdefault(row["at"], row)
        rows = list(by_instant.values())
        try:
            async with self._conn.begin_nested():
                await self._conn.execute(delete(readings).where(readings.c.meter_id == meter_id))
                return await insert_rows(self._conn, readings, rows)
        except IntegrityError as exc:
            if "FOREIGN KEY" in str(exc.orig):
                raise NotFoundError(f"meter {meter_id} not in index") from exc
            raise

    async def list(self, meter_id: str, start: date | None, end: date | None) -> list[Reading]:
        lo, hi = mapping.ist_day_bounds(start, end)
        stmt = select(readings).where(readings.c.meter_id == meter_id).order_by(readings.c.at)
        if lo is not None:
            stmt = stmt.where(readings.c.at >= lo)
        if hi is not None:
            stmt = stmt.where(readings.c.at < hi)
        result = await self._conn.execute(stmt)
        return [mapping.row_to_reading(r) for r in result.mappings()]

    async def count(self) -> int:
        return (await self._conn.execute(select(func.count()).select_from(readings))).scalar_one()
