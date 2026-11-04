"""SQLite implementation of SyncRepository."""

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.db.tables import sync_runs
from app.domain.exceptions import ConflictError, NotFoundError
from app.domain.models import SyncRun, SyncStatus, SyncStrategy
from app.repositories.sqlite import mapping


class SqliteSyncRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def start_run(self, started_at: datetime) -> SyncRun:
        """The partial unique index lets only one 'running' row exist; a clash is a conflict."""
        values: dict[str, Any] = {
            "status": SyncStatus.RUNNING.value,
            "started_at": mapping.utc_text(started_at),
            "counts": "{}",
        }
        try:
            async with self._conn.begin_nested():
                result = await self._conn.execute(insert(sync_runs).values(**values))
        except IntegrityError as exc:
            raise ConflictError("a sync is already running") from exc
        except OperationalError as exc:  # a concurrent writer holds the lock
            if "locked" in str(exc.orig) or "busy" in str(exc.orig):
                raise ConflictError("a sync is already running") from exc
            raise
        assert result.inserted_primary_key is not None
        return await self._get(result.inserted_primary_key[0])

    async def finish_run(
        self,
        run_id: int,
        *,
        status: SyncStatus,
        strategy: SyncStrategy | None,
        finished_at: datetime,
        counts: Mapping[str, int],
        error: str | None,
    ) -> SyncRun:
        result = await self._conn.execute(
            update(sync_runs)
            .where(sync_runs.c.id == run_id)
            .values(
                status=status.value,
                strategy=strategy.value if strategy else None,
                finished_at=mapping.utc_text(finished_at),
                counts=mapping.counts_to_json(counts),
                error=error,
            )
        )
        if result.rowcount == 0:
            raise NotFoundError(f"sync run {run_id} not found")
        return await self._get(run_id)

    async def current(self) -> SyncRun | None:
        return await self._first(
            select(sync_runs).where(sync_runs.c.status == SyncStatus.RUNNING.value)
        )

    async def last_successful(self) -> SyncRun | None:
        stmt = (
            select(sync_runs)
            .where(sync_runs.c.status == SyncStatus.SUCCEEDED.value)
            .order_by(sync_runs.c.finished_at.desc(), sync_runs.c.id.desc())
        )
        return await self._first(stmt)

    async def latest(self) -> SyncRun | None:
        return await self._first(select(sync_runs).order_by(sync_runs.c.id.desc()))

    async def fail_stale_runs(self, finished_at: datetime, error: str) -> int:
        result = await self._conn.execute(
            update(sync_runs)
            .where(sync_runs.c.status == SyncStatus.RUNNING.value)
            .values(
                status=SyncStatus.FAILED.value,
                finished_at=mapping.utc_text(finished_at),
                error=error,
            )
        )
        return result.rowcount

    async def _get(self, run_id: int) -> SyncRun:
        run = await self._first(select(sync_runs).where(sync_runs.c.id == run_id))
        assert run is not None
        return run

    async def _first(self, stmt: Any) -> SyncRun | None:
        row = (await self._conn.execute(stmt)).mappings().first()
        return mapping.row_to_sync_run(row) if row else None
