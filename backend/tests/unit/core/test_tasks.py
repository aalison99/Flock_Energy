import asyncio
import logging

import pytest

from app.core.tasks import AsyncioTaskRunner

pytestmark = pytest.mark.anyio


async def test_spawn_runs_the_coroutine() -> None:
    runner = AsyncioTaskRunner()
    done = asyncio.Event()

    async def work() -> None:
        done.set()

    runner.spawn("work", work())
    await asyncio.wait_for(done.wait(), 1)
    await runner.aclose()


async def test_finished_tasks_are_dropped() -> None:
    runner = AsyncioTaskRunner()

    async def work() -> None:
        return None

    runner.spawn("work", work())
    assert runner.active == 1  # a strong reference is held while it runs
    for _ in range(5):
        await asyncio.sleep(0)
    assert runner.active == 0


async def test_exception_is_logged_with_traceback(caplog: pytest.LogCaptureFixture) -> None:
    runner = AsyncioTaskRunner()

    async def boom() -> None:
        raise RuntimeError("kaput")

    with caplog.at_level(logging.ERROR, logger="urja.tasks"):
        runner.spawn("boom-task", boom())
        for _ in range(5):
            await asyncio.sleep(0)
    record = next(r for r in caplog.records if r.levelno == logging.ERROR)
    assert "boom-task" in record.getMessage()
    assert record.exc_info is not None
    assert record.exc_info[0] is RuntimeError
    assert runner.active == 0


async def test_aclose_cancels_and_awaits_running_tasks() -> None:
    runner = AsyncioTaskRunner()
    started = asyncio.Event()
    cleaned: list[bool] = []

    async def forever() -> None:
        started.set()
        try:
            await asyncio.sleep(3600)
        finally:
            cleaned.append(True)

    runner.spawn("forever", forever())
    await started.wait()
    await runner.aclose()
    assert cleaned == [True]
    assert runner.active == 0


async def test_cancelled_task_is_not_logged_as_error(caplog: pytest.LogCaptureFixture) -> None:
    runner = AsyncioTaskRunner()

    async def forever() -> None:
        await asyncio.sleep(3600)

    with caplog.at_level(logging.ERROR, logger="urja.tasks"):
        runner.spawn("forever", forever())
        await asyncio.sleep(0)
        await runner.aclose()
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


async def test_aclose_times_out_on_a_task_that_ignores_cancellation(
    caplog: pytest.LogCaptureFixture,
) -> None:
    runner = AsyncioTaskRunner()
    started = asyncio.Event()
    release = asyncio.Event()

    async def stubborn() -> None:
        started.set()
        while not release.is_set():
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                await asyncio.sleep(0.05)  # swallows the cancel and keeps going

    runner.spawn("stubborn", stubborn())
    await started.wait()
    with caplog.at_level(logging.WARNING, logger="urja.tasks"):
        await asyncio.wait_for(runner.aclose(timeout_s=0.1), 2)
    assert any("stubborn" in r.getMessage() for r in caplog.records if r.levelno == logging.WARNING)
    release.set()
    await asyncio.sleep(0.1)
