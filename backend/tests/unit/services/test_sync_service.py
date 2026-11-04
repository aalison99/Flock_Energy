import asyncio
import gc
import logging
import warnings
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from functools import partial

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.domain.exceptions import (
    ConflictError,
    UpstreamAuthError,
    UpstreamProtocolError,
    UpstreamUnavailableError,
)
from app.domain.models import Meter, SyncRun, SyncStatus, SyncStrategy, Transformer
from app.portal.breaker import CircuitBreaker
from app.portal.fake import FakePortalClient
from app.portal.interfaces import PortalClient, PortalPage
from app.portal.retrying import RetryingClient, RetryPolicy
from app.repositories.sqlite.store import SqliteIndexStore
from app.repositories.sqlite.sync_repo import SqliteSyncRepository
from app.services import sync_service
from app.services.sync_service import SyncService
from tests.support.fake_clock import FakeClock, FakeSleeper
from tests.support.portal_emulator import FIXTURES
from tests.support.portals import ProbedPortal, SubsetPortal
from tests.support.tasks import ManualTaskRunner

pytestmark = pytest.mark.anyio
T0 = datetime(2026, 11, 4, 9, tzinfo=UTC)
WITH_READINGS = ("J100000", "J100402")  # the fixtures hold energy files for these two meters


@dataclass
class Rig:
    service: SyncService
    store: SqliteIndexStore
    tasks: ManualTaskRunner
    clock: FakeClock

    async def sync(self, include_readings: bool = True) -> SyncRun:
        run = await self.service.start(include_readings)
        await self.tasks.run_all()
        async with self.store.transaction() as repos:
            latest = await repos.runs.latest()
        assert latest is not None
        assert latest.id == run.id
        return latest

    async def snapshot(self) -> tuple[list[object], list[object], int]:
        async with self.store.transaction() as repos:
            return (
                list(await repos.meters.list_all()),
                list(await repos.transformers.list_all()),
                await repos.readings.count(),
            )


def make_rig(engine: AsyncEngine, portal: PortalClient, concurrency: int = 4) -> Rig:
    store = SqliteIndexStore(engine)
    tasks = ManualTaskRunner()
    clock = FakeClock(T0)
    return Rig(
        SyncService(portal, store, tasks, clock, concurrency=concurrency), store, tasks, clock
    )


@pytest.fixture
def fake() -> FakePortalClient:
    return FakePortalClient(FIXTURES)


@pytest.fixture
def rig(engine: AsyncEngine, fake: FakePortalClient) -> Rig:
    return make_rig(engine, fake)


async def test_first_sync_fills_the_index(rig: Rig, fake: FakePortalClient) -> None:
    started = await rig.service.start(include_readings=True)
    assert started.status is SyncStatus.RUNNING
    assert rig.tasks.names == ["sync"]
    await rig.tasks.run_all()

    run = (await rig.service.status()).latest
    assert run is not None
    assert (run.id, run.status, run.strategy) == (
        started.id,
        SyncStatus.SUCCEEDED,
        SyncStrategy.EXPORT,
    )
    assert run.error is None
    assert run.finished_at == T0
    counts = dict(run.counts)
    assert counts["meters"] == 403
    assert counts["meters_removed"] == 0
    assert counts["transformers"] == 40
    assert counts["transformers_removed"] == 0
    assert counts["readings_meters"] == 403
    assert counts["readings_failed"] == 0
    assert counts["readings"] > 0
    assert set(counts) == {
        "meters",
        "meters_removed",
        "transformers",
        "transformers_removed",
        "readings",
        "readings_meters",
        "readings_failed",
    }
    meters, transformers, reading_rows = await rig.snapshot()
    assert (len(meters), len(transformers), reading_rows) == (403, 40, counts["readings"])
    assert not any(c[0] in ("get_meter", "get_geo", "list_meters") for c in fake.calls)
    assert sum(1 for c in fake.calls if c[0] == "get_readings") == 403


async def test_second_sync_is_idempotent(rig: Rig) -> None:
    first = await rig.sync()
    before = await rig.snapshot()
    rig.clock.advance(3600)
    second = await rig.sync()
    assert await rig.snapshot() == before
    assert dict(second.counts) == dict(first.counts)
    assert second.id != first.id
    assert second.finished_at == T0.replace(hour=10)


async def test_export_failure_falls_back_to_crawl_with_same_meters(
    engine: AsyncEngine, fake: FakePortalClient, caplog: pytest.LogCaptureFixture
) -> None:
    exported = make_rig(engine, fake)
    await exported.sync(include_readings=False)
    expected = await exported.snapshot()

    crawl_portal = FakePortalClient(FIXTURES)
    crawl_portal.fail("bulk_export", UpstreamUnavailableError("down"))
    crawl = make_rig(engine, crawl_portal)
    with caplog.at_level(logging.WARNING, logger="urja.sync"):
        run = await crawl.sync(include_readings=False)
    assert run.status is SyncStatus.SUCCEEDED
    assert run.strategy is SyncStrategy.CRAWL
    assert await crawl.snapshot() == expected
    warning = next(r for r in caplog.records if r.levelno == logging.WARNING)
    assert (
        warning.getMessage()
        == "bulk export failed (UpstreamUnavailableError); falling back to crawl"
    )
    methods = [c[0] for c in crawl_portal.calls]
    assert methods.count("list_meters") == 21  # 403 meters, 20 per page
    assert methods.count("get_meter") == methods.count("get_geo") == 403


async def test_crawl_never_exceeds_the_concurrency_limit(engine: AsyncEngine) -> None:
    portal = ProbedPortal(FIXTURES)
    portal.fail("bulk_export", UpstreamUnavailableError("down"))
    rig = make_rig(engine, portal, concurrency=3)
    run = await rig.sync(include_readings=True)
    assert run.status is SyncStatus.SUCCEEDED
    assert portal.max_in_flight == 3  # reached, never exceeded (crawl and readings phases)


async def test_meter_missing_upstream_is_removed_with_its_readings(
    engine: AsyncEngine, fake: FakePortalClient
) -> None:
    first = make_rig(engine, fake)
    await first.sync()
    keep = [m.meter_id for m in await fake.bulk_export() if m.meter_id != WITH_READINGS[0]]
    shrunk = make_rig(engine, SubsetPortal(FIXTURES, keep))
    run = await shrunk.sync()
    assert run.status is SyncStatus.SUCCEEDED
    assert dict(run.counts)["meters"] == 402
    assert dict(run.counts)["meters_removed"] == 1
    async with shrunk.store.transaction() as repos:
        assert await repos.meters.get(WITH_READINGS[0]) is None
        assert await repos.readings.list(WITH_READINGS[0], None, None) == []
        assert await repos.readings.list(WITH_READINGS[1], None, None)
        assert await repos.meters.count() == 402


async def test_empty_export_fails_and_leaves_the_index_unchanged(
    engine: AsyncEngine, fake: FakePortalClient
) -> None:
    await make_rig(engine, fake).sync()
    empty = make_rig(engine, SubsetPortal(FIXTURES, []))
    before = await empty.snapshot()
    run = await empty.sync()
    assert run.status is SyncStatus.FAILED
    assert run.error == "portal returned no meters; index left unchanged"
    assert await empty.snapshot() == before


async def test_transformer_failure_fails_the_run_and_writes_nothing(
    rig: Rig, fake: FakePortalClient
) -> None:
    fake.fail("list_transformers", UpstreamUnavailableError("dts down"), times=5)
    run = await rig.sync()
    assert run.status is SyncStatus.FAILED
    assert run.error == "UpstreamUnavailableError: dts down"
    assert run.strategy is SyncStrategy.EXPORT
    assert await rig.snapshot() == ([], [], 0)


async def test_unexpected_exception_records_only_the_class_name(
    rig: Rig, fake: FakePortalClient
) -> None:
    fake.fail("list_transformers", RuntimeError("secret detail"))
    run = await rig.sync()
    assert run.status is SyncStatus.FAILED
    assert run.error == "RuntimeError"


async def test_crawl_failure_fails_the_run(engine: AsyncEngine) -> None:
    portal = FakePortalClient(FIXTURES)
    portal.fail("bulk_export", UpstreamUnavailableError("down"))
    portal.fail("get_meter", UpstreamUnavailableError("meter down"), on_call=5, times=1)
    run = await make_rig(engine, portal).sync()
    assert run.status is SyncStatus.FAILED
    assert run.strategy is SyncStrategy.CRAWL
    assert run.error == "UpstreamUnavailableError: meter down"


async def test_per_meter_reading_failure_is_counted_and_the_run_succeeds(
    rig: Rig, fake: FakePortalClient, caplog: pytest.LogCaptureFixture
) -> None:
    fake.fail("get_readings", UpstreamUnavailableError("flaky"), on_call=3, times=1)
    with caplog.at_level(logging.WARNING, logger="urja.sync"):
        run = await rig.sync()
    assert run.status is SyncStatus.SUCCEEDED
    counts = dict(run.counts)
    assert counts["readings_failed"] == 1
    assert counts["readings_meters"] == 402
    assert any("UpstreamUnavailableError" in r.getMessage() for r in caplog.records)


async def test_retries_between_sync_and_portal_absorb_transient_reading_failures(
    engine: AsyncEngine, fake: FakePortalClient
) -> None:
    clock = FakeClock(T0)
    fake.fail("get_readings", UpstreamUnavailableError("429"), times=2)  # the first two calls
    flaky = RetryingClient(
        fake,
        policy=RetryPolicy(attempts=3, base_delay_s=0.25, max_delay_s=1.0, retry_after_cap_s=30),
        breaker=CircuitBreaker(failure_threshold=10, reset_s=30, clock=clock),
        sleep=FakeSleeper(clock),
    )
    run = await make_rig(engine, flaky).sync()
    assert run.status is SyncStatus.SUCCEEDED
    assert dict(run.counts)["readings_failed"] == 0
    assert dict(run.counts)["readings_meters"] == 403
    assert sum(1 for c in fake.calls if c[0] == "get_readings") == 403 + 2


async def test_without_readings_no_reading_calls(rig: Rig, fake: FakePortalClient) -> None:
    run = await rig.sync(include_readings=False)
    assert run.status is SyncStatus.SUCCEEDED
    assert not any(c[0] == "get_readings" for c in fake.calls)
    counts = dict(run.counts)
    assert (counts["readings"], counts["readings_meters"], counts["readings_failed"]) == (0, 0, 0)
    assert (await rig.snapshot())[2] == 0


async def test_start_while_running_conflicts(rig: Rig) -> None:
    await rig.service.start(include_readings=False)
    with pytest.raises(ConflictError):
        await rig.service.start(include_readings=False)
    assert rig.tasks.names == ["sync"]  # the rejected start spawned nothing
    rig.tasks.discard()


async def test_status_and_index_info_before_and_after(rig: Rig) -> None:
    status = await rig.service.status()
    assert (status.latest, status.last_successful) == (None, None)
    info = await rig.service.index_info()
    assert (info.ready, info.meter_count, info.last_sync_at) == (False, 0, None)

    started = await rig.service.start(include_readings=False)
    running = await rig.service.status()
    assert running.latest == started
    assert running.last_successful is None
    await rig.tasks.run_all()

    done = await rig.service.status()
    assert done.latest is not None and done.latest.status is SyncStatus.SUCCEEDED
    assert done.last_successful == done.latest
    info = await rig.service.index_info()
    assert (info.ready, info.meter_count, info.last_sync_at) == (True, 403, T0)


async def test_progress_counts_are_exact_mid_run(
    engine: AsyncEngine, fake: FakePortalClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sync_service, "PROGRESS_EVERY", 2)
    rig = make_rig(engine, fake, concurrency=1)
    third_call = asyncio.Event()
    release = asyncio.Event()
    real = fake.get_readings
    calls = 0

    async def gated(meter_id: str, start: object = None, end: object = None) -> list:  # type: ignore[type-arg]
        nonlocal calls
        calls += 1
        if calls == 3:
            third_call.set()
            await release.wait()
        return await real(meter_id)

    fake.get_readings = gated  # type: ignore[method-assign]
    await rig.service.start(include_readings=True)
    task = asyncio.create_task(rig.tasks.run_all())
    await asyncio.wait_for(third_call.wait(), 5)
    mid = (await rig.service.status()).latest
    assert mid is not None and mid.status is SyncStatus.RUNNING
    assert dict(mid.counts)["meters"] == 403  # the write phase is already visible
    assert dict(mid.counts)["readings_meters"] == 2  # exactly the two meters before the write
    release.set()
    await task


async def test_progress_write_failure_is_logged_and_the_run_continues(
    engine: AsyncEngine,
    fake: FakePortalClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(sync_service, "PROGRESS_EVERY", 100)
    rig = make_rig(engine, fake)
    real = SqliteSyncRepository.update_counts
    seen = 0

    async def flaky(self: SqliteSyncRepository, run_id: int, counts: Mapping[str, int]) -> None:
        nonlocal seen
        seen += 1
        if seen > 1:  # the first call is the write phase; the progress writes fail
            raise OperationalError("UPDATE", {}, Exception("database is locked"))
        await real(self, run_id, counts)

    monkeypatch.setattr(SqliteSyncRepository, "update_counts", flaky)
    with caplog.at_level(logging.WARNING, logger="urja.sync"):
        run = await rig.sync()
    assert run.status is SyncStatus.SUCCEEDED
    assert dict(run.counts)["readings_meters"] == 403
    assert any("progress" in r.getMessage() for r in caplog.records)


async def test_empty_transformer_list_keeps_existing_ones_and_warns(
    engine: AsyncEngine, fake: FakePortalClient, caplog: pytest.LogCaptureFixture
) -> None:
    await make_rig(engine, fake).sync(include_readings=False)
    empty_dts = FakePortalClient(FIXTURES)

    async def none_listed(page: int) -> PortalPage[Transformer]:
        return PortalPage(items=(), total=0, page=page, page_size=20)

    empty_dts.list_transformers = none_listed  # type: ignore[method-assign]
    rig = make_rig(engine, empty_dts)
    with caplog.at_level(logging.WARNING, logger="urja.sync"):
        run = await rig.sync(include_readings=False)
    assert run.status is SyncStatus.SUCCEEDED
    assert dict(run.counts)["transformers"] == 0
    assert dict(run.counts)["transformers_removed"] == 0
    assert (await rig.snapshot())[1].__len__() == 40
    assert any("no transformers" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize(
    "error",
    [
        UpstreamAuthError("auth"),
        UpstreamProtocolError("proto"),
        UpstreamUnavailableError("down"),
    ],
)
async def test_each_export_failure_kind_falls_back_to_crawl(
    engine: AsyncEngine, error: Exception
) -> None:
    portal = FakePortalClient(FIXTURES)
    portal.fail("bulk_export", error)
    run = await make_rig(engine, portal).sync(include_readings=False)
    assert run.status is SyncStatus.SUCCEEDED
    assert run.strategy is SyncStrategy.CRAWL
    assert dict(run.counts)["meters"] == 403


async def test_duplicate_meter_ids_keep_the_first_and_are_counted_once(
    engine: AsyncEngine, caplog: pytest.LogCaptureFixture
) -> None:
    portal = FakePortalClient(FIXTURES)
    real = portal.bulk_export

    async def with_dupes() -> list[Meter]:
        meters = await real()
        return [*meters, replace(meters[0], serial_no="DUPLICATE"), meters[1]]

    portal.bulk_export = with_dupes  # type: ignore[method-assign]
    rig = make_rig(engine, portal)
    with caplog.at_level(logging.WARNING, logger="urja.sync"):
        run = await rig.sync(include_readings=False)
    assert dict(run.counts)["meters"] == 403
    first = (await real())[0]
    async with rig.store.transaction() as repos:
        assert await repos.meters.get(first.meter_id) == first
    assert any("2 duplicate" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize(
    ("sizes", "total", "expected_calls"),
    [
        ([], 0, 1),  # nothing at all: one request, stop
        ([20], 20, 1),  # a total that is exactly one full page
        ([20, 20], 40, 2),  # exact multiple of the page size: no third request
        ([20, 20, 5], 45, 3),  # short last page
        ([20, 20], 100, 3),  # an over-large total ends on the empty page
    ],
)
async def test_paging_stops_at_total_or_a_short_page(
    sizes: list[int], total: int, expected_calls: int
) -> None:
    fetched: list[int] = []

    async def fetch(page: int) -> PortalPage[int]:
        fetched.append(page)
        size = sizes[page - 1] if page <= len(sizes) else 0
        return PortalPage(items=tuple(range(size)), total=total, page=page, page_size=20)

    items = await sync_service.all_pages(fetch)
    assert len(items) == sum(sizes)
    assert len(fetched) == expected_calls


async def test_bounded_creates_no_coroutine_that_is_never_awaited() -> None:
    started: list[int] = []

    async def job(n: int) -> int:
        started.append(n)
        if n == 0:
            raise RuntimeError("first fails")
        await asyncio.sleep(0)
        return n

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        with pytest.raises(RuntimeError):
            await SyncService._bounded([partial(job, n) for n in range(50)], 1)
        gc.collect()
    assert started[0] == 0
    assert len(started) < 5  # the rest were never even created, so none is left unawaited


async def test_cancellation_marks_the_run_failed_cancelled(
    engine: AsyncEngine, fake: FakePortalClient
) -> None:
    gate = asyncio.Event()
    entered = asyncio.Event()
    real = fake.bulk_export

    async def slow_export() -> list:  # type: ignore[type-arg]
        entered.set()
        await gate.wait()
        return await real()

    fake.bulk_export = slow_export  # type: ignore[method-assign]
    rig = make_rig(engine, fake)
    await rig.service.start(include_readings=False)
    task = asyncio.create_task(rig.tasks.run_all())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    latest = (await rig.service.status()).latest
    assert latest is not None
    assert (latest.status, latest.error) == (SyncStatus.FAILED, "cancelled")
    assert latest.finished_at == T0
    # and a new run may start afterwards
    await rig.service.start(include_readings=False)
    rig.tasks.discard()
