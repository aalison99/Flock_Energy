"""SQLite implementation of ReadingRepository."""

from collections.abc import Collection, Sequence
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

_CHUNK = 500  # bind parameters per IN (...) statement


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

    async def list_for_meters(
        self, meter_ids: Collection[str] | None, start: date | None, end: date | None
    ) -> dict[str, list[Reading]]:
        lo, hi = mapping.ist_day_bounds(start, end)
        base = select(readings).order_by(readings.c.meter_id, readings.c.at)
        if lo is not None:
            base = base.where(readings.c.at >= lo)
        if hi is not None:
            base = base.where(readings.c.at < hi)
        ids = None if meter_ids is None else sorted(set(meter_ids))
        batches = (
            [None] if ids is None else [ids[i : i + _CHUNK] for i in range(0, len(ids), _CHUNK)]
        )
        grouped: dict[str, list[Reading]] = {}
        for batch in batches:
            stmt = base if batch is None else base.where(readings.c.meter_id.in_(batch))
            for row in (await self._conn.execute(stmt)).mappings():
                grouped.setdefault(row["meter_id"], []).append(mapping.row_to_reading(row))
        return dict(sorted(grouped.items()))

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
