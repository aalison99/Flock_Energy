"""Repository Protocols: what services may ask of local storage (async, queries only).

Each repository works on the connection it was built with, so the caller's transaction is
the unit of work.
"""

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Protocol

from app.domain.models import Meter, Reading, SyncRun, SyncStatus, SyncStrategy, Transformer


class MeterRepository(Protocol):
    async def upsert_many(self, meters: Sequence[Meter], synced_at: datetime) -> int:
        """Insert or update meters by id; returns rows written."""
        ...

    async def get(self, meter_id: str) -> Meter | None: ...

    async def count(self) -> int: ...

    async def list_all(self) -> list[Meter]:
        """Every meter, ordered by meter_id."""
        ...


class TransformerRepository(Protocol):
    async def upsert_many(self, transformers: Sequence[Transformer], synced_at: datetime) -> int:
        """Insert or update transformers by code; returns rows written."""
        ...

    async def get(self, code: str) -> Transformer | None: ...

    async def list_all(self) -> list[Transformer]:
        """Every transformer, ordered by code."""
        ...

    async def count(self) -> int: ...


class ReadingRepository(Protocol):
    async def replace_for_meter(self, meter_id: str, readings: Sequence[Reading]) -> int:
        """Atomically delete the meter's readings and insert these; returns rows inserted."""
        ...

    async def list(self, meter_id: str, start: date | None, end: date | None) -> list[Reading]:
        """Readings ascending by time within the inclusive IST calendar days."""
        ...

    async def count(self) -> int: ...


class SyncRepository(Protocol):
    async def start_run(self, started_at: datetime) -> SyncRun:
        """Open a run; raises ConflictError if one is already running."""
        ...

    async def finish_run(
        self,
        run_id: int,
        *,
        status: SyncStatus,
        strategy: SyncStrategy | None,
        finished_at: datetime,
        counts: Mapping[str, int],
        error: str | None,
    ) -> SyncRun: ...

    async def current(self) -> SyncRun | None:
        """The running run, if any."""
        ...

    async def last_successful(self) -> SyncRun | None: ...

    async def latest(self) -> SyncRun | None: ...

    async def fail_stale_runs(self, finished_at: datetime, error: str) -> int:
        """Mark leftover 'running' rows failed (crash recovery); returns rows changed."""
        ...
