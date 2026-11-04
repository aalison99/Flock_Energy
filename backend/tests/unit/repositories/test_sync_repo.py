from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.domain.exceptions import ConflictError, NotFoundError
from app.domain.models import SyncStatus, SyncStrategy
from app.repositories.sqlite.sync_repo import SqliteSyncRepository

pytestmark = pytest.mark.anyio
T0 = datetime(2026, 7, 1, 12, tzinfo=UTC)


def at(minutes: int) -> datetime:
    return T0 + timedelta(minutes=minutes)


async def _finish(
    repo: SqliteSyncRepository, run_id: int, status: SyncStatus, minutes: int
) -> None:
    await repo.finish_run(
        run_id,
        status=status,
        strategy=SyncStrategy.EXPORT,
        finished_at=at(minutes),
        counts={"meters": 3},
        error=None if status is SyncStatus.SUCCEEDED else "boom",
    )


async def test_empty_state(engine: AsyncEngine) -> None:
    async with engine.begin() as c:
        repo = SqliteSyncRepository(c)
        assert await repo.current() is None
        assert await repo.latest() is None
        assert await repo.last_successful() is None


async def test_start_and_finish_run(engine: AsyncEngine) -> None:
    async with engine.begin() as c:
        repo = SqliteSyncRepository(c)
        run = await repo.start_run(T0)
        assert (run.status, run.started_at, run.finished_at, dict(run.counts)) == (
            SyncStatus.RUNNING,
            T0,
            None,
            {},
        )
        assert await repo.current() == run
        done = await repo.finish_run(
            run.id,
            status=SyncStatus.SUCCEEDED,
            strategy=SyncStrategy.CRAWL,
            finished_at=at(5),
            counts={"meters": 7, "readings": 0},
            error=None,
        )
        assert done.status is SyncStatus.SUCCEEDED
        assert done.strategy is SyncStrategy.CRAWL
        assert done.finished_at == at(5)
        assert dict(done.counts) == {"meters": 7, "readings": 0}
        assert await repo.current() is None
        assert await repo.last_successful() == done


async def test_finish_unknown_run_is_not_found(engine: AsyncEngine) -> None:
    async with engine.begin() as c:
        with pytest.raises(NotFoundError):
            await SqliteSyncRepository(c).finish_run(
                99,
                status=SyncStatus.FAILED,
                strategy=None,
                finished_at=T0,
                counts={},
                error="x",
            )


async def test_second_start_conflicts_on_same_connection(engine: AsyncEngine) -> None:
    async with engine.begin() as c:
        repo = SqliteSyncRepository(c)
        await repo.start_run(T0)
        with pytest.raises(ConflictError, match="already running"):
            await repo.start_run(at(1))
        assert (await repo.current()) is not None  # connection still usable


async def test_conflict_across_two_connections(engine: AsyncEngine) -> None:
    async with engine.begin() as a:
        first = await SqliteSyncRepository(a).start_run(T0)
    async with engine.begin() as b:
        with pytest.raises(ConflictError):
            await SqliteSyncRepository(b).start_run(at(1))
    async with engine.begin() as c:
        repo = SqliteSyncRepository(c)
        await _finish(repo, first.id, SyncStatus.FAILED, 2)
        again = await repo.start_run(at(3))  # allowed once the first is finished
        assert again.id != first.id


async def test_latest_and_last_successful_ordering(engine: AsyncEngine) -> None:
    async with engine.begin() as c:
        repo = SqliteSyncRepository(c)
        r1 = await repo.start_run(at(0))
        await _finish(repo, r1.id, SyncStatus.SUCCEEDED, 1)
        r2 = await repo.start_run(at(10))
        await _finish(repo, r2.id, SyncStatus.SUCCEEDED, 11)
        r3 = await repo.start_run(at(20))
        await _finish(repo, r3.id, SyncStatus.FAILED, 21)
        latest = await repo.latest()
        assert latest is not None and latest.id == r3.id
        ok = await repo.last_successful()
        assert ok is not None and ok.id == r2.id
        r4 = await repo.start_run(at(30))
        running = await repo.latest()
        assert running is not None and running.id == r4.id


async def test_fail_stale_runs(engine: AsyncEngine) -> None:
    async with engine.begin() as c:
        repo = SqliteSyncRepository(c)
        done = await repo.start_run(at(0))
        await _finish(repo, done.id, SyncStatus.SUCCEEDED, 1)
        stale = await repo.start_run(at(2))
        assert await repo.fail_stale_runs(at(9), "interrupted: process restarted") == 1
        assert await repo.current() is None
        latest = await repo.latest()
        assert latest is not None and latest.id == stale.id
        assert latest.status is SyncStatus.FAILED
        assert latest.finished_at == at(9)
        assert latest.error == "interrupted: process restarted"
        assert await repo.fail_stale_runs(at(10), "x") == 0
        ok = await repo.last_successful()
        assert ok is not None and ok.id == done.id


async def test_start_run_as_first_statement_rolls_back_with_caller(engine: AsyncEngine) -> None:
    with pytest.raises(RuntimeError):
        async with engine.begin() as c:
            await SqliteSyncRepository(c).start_run(T0)
            raise RuntimeError("boom")
    async with engine.begin() as c:
        assert await SqliteSyncRepository(c).current() is None


async def test_uncommitted_concurrent_start_run_is_a_conflict(db_url: str) -> None:
    from app.db.engine import make_async_engine

    eng = make_async_engine(db_url, busy_timeout_ms=100)
    try:
        async with eng.connect() as a:
            ta = await a.begin()
            await SqliteSyncRepository(a).start_run(T0)
            async with eng.begin() as b:
                with pytest.raises(ConflictError, match="already running"):
                    await SqliteSyncRepository(b).start_run(at(1))
            await ta.rollback()
    finally:
        await eng.dispose()
