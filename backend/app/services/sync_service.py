"""SyncService: fills the local index from the portal in the background.

`start` opens a run and hands the work to a TaskRunner; `_run` fetches everything first and
writes in one transaction, so a failed fetch never leaves the index half-updated.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import replace
from functools import partial

from app.core.interfaces import Clock, TaskRunner
from app.domain.exceptions import (
    DomainError,
    UpstreamAuthError,
    UpstreamProtocolError,
    UpstreamUnavailableError,
)
from app.domain.models import Meter, SyncRun, SyncStatus, SyncStrategy, Transformer
from app.portal.interfaces import PortalClient, PortalPage
from app.repositories.interfaces import IndexStore
from app.services.results import IndexInfo, SyncStatusResult

logger = logging.getLogger("urja.sync")

PROGRESS_EVERY = 50  # meters between progress writes in the readings phase
_EXPORT_FALLBACK_ERRORS = (UpstreamAuthError, UpstreamProtocolError, UpstreamUnavailableError)


class _Abort(Exception):
    """A deliberate stop; its message is recorded as the run's error verbatim."""


class SyncService:
    def __init__(
        self,
        portal: PortalClient,
        store: IndexStore,
        tasks: TaskRunner,
        clock: Clock,
        *,
        concurrency: int,
    ) -> None:
        self._portal = portal
        self._store = store
        self._tasks = tasks
        self._clock = clock
        self._concurrency = concurrency

    async def start(self, include_readings: bool) -> SyncRun:
        """Open a run (ConflictError if one is running) and continue it in the background."""
        async with self._store.transaction() as repos:
            run = await repos.runs.start_run(self._clock.now())
        self._tasks.spawn("sync", self._run(run.id, include_readings))
        return run

    async def status(self) -> SyncStatusResult:
        async with self._store.transaction() as repos:
            return SyncStatusResult(
                latest=await repos.runs.latest(), last_successful=await repos.runs.last_successful()
            )

    async def index_info(self) -> IndexInfo:
        async with self._store.transaction() as repos:
            count = await repos.meters.count()
            last = await repos.runs.last_successful()
        return IndexInfo(
            ready=count > 0,
            meter_count=count,
            last_sync_at=last.finished_at if last else None,
        )

    async def _run(self, run_id: int, include_readings: bool) -> None:
        counts: dict[str, int] = {}
        strategy: SyncStrategy | None = None
        try:
            meters = await self._try_export()
            strategy = SyncStrategy.EXPORT if meters is not None else SyncStrategy.CRAWL
            if meters is None:
                meters = await self._crawl()
            meters = _unique_by_id(meters)
            transformers = await self._fetch_transformers()
            if not meters:
                raise _Abort("portal returned no meters; index left unchanged")
            await self._write(run_id, meters, transformers, counts)
            counts.update(readings=0, readings_meters=0, readings_failed=0)
            if include_readings:
                await self._sync_readings(run_id, [m.meter_id for m in meters], counts)
            await self._finish(run_id, SyncStatus.SUCCEEDED, strategy, counts, None)
            logger.info("sync %d succeeded: %s", run_id, counts)
        except asyncio.CancelledError:
            logger.warning("sync %d cancelled", run_id)
            await self._finish_quietly(run_id, strategy, counts, "cancelled")
            raise
        except Exception as exc:
            error = _describe(exc)
            logger.error("sync %d failed: %s", run_id, error, exc_info=not _expected(exc))
            await self._finish_quietly(run_id, strategy, counts, error)

    # -- phase 1: meters ---------------------------------------------------------------------

    async def _try_export(self) -> list[Meter] | None:
        """The bulk export, or None when the portal refuses it (the caller then crawls)."""
        try:
            meters = await self._portal.bulk_export()
        except _EXPORT_FALLBACK_ERRORS as exc:
            logger.warning("bulk export failed (%s); falling back to crawl", type(exc).__name__)
            return None
        logger.info("meters: %d via bulk export", len(meters))
        return meters

    async def _crawl(self) -> list[Meter]:
        listed = await all_pages(self._portal.list_meters)
        found = await self._bounded(
            [partial(self._crawl_one, m.meter_id) for m in listed], self._concurrency
        )
        logger.info("meters: %d via crawl", len(found))
        return found

    async def _crawl_one(self, meter_id: str) -> Meter:
        meter = await self._portal.get_meter(meter_id)
        geo = await self._portal.get_geo(meter_id)
        return replace(meter, geo=geo)

    # -- phase 2: transformers ---------------------------------------------------------------

    async def _fetch_transformers(self) -> list[Transformer]:
        items = await all_pages(self._portal.list_transformers)
        logger.info("transformers: %d", len(items))
        return items

    # -- phase 3: write ----------------------------------------------------------------------

    async def _write(
        self,
        run_id: int,
        meters: list[Meter],
        transformers: list[Transformer],
        counts: dict[str, int],
    ) -> None:
        synced_at = self._clock.now()
        async with self._store.transaction() as repos:
            counts["meters"] = await repos.meters.upsert_many(meters, synced_at)
            counts["meters_removed"] = await repos.meters.delete_missing(
                {m.meter_id for m in meters}
            )
            counts["transformers"] = await repos.transformers.upsert_many(transformers, synced_at)
            if transformers:
                removed = await repos.transformers.delete_missing({t.code for t in transformers})
            else:  # an empty listing is more likely a portal hiccup than an empty grid
                logger.warning("portal returned no transformers; keeping existing ones")
                removed = 0
            counts["transformers_removed"] = removed
            await repos.runs.update_counts(run_id, counts)
        logger.info("written: %s", counts)

    # -- phase 4: readings -------------------------------------------------------------------

    async def _sync_readings(
        self, run_id: int, meter_ids: list[str], counts: dict[str, int]
    ) -> None:
        done = 0

        async def one(meter_id: str) -> None:
            nonlocal done
            try:
                readings = await self._portal.get_readings(meter_id)
                async with self._store.transaction() as repos:
                    stored = await repos.readings.replace_for_meter(meter_id, readings)
                counts["readings"] += stored
                counts["readings_meters"] += 1
            except DomainError as exc:
                counts["readings_failed"] += 1
                logger.warning("readings for %s failed (%s)", meter_id, type(exc).__name__)
            done += 1
            if done % PROGRESS_EVERY == 0:
                await self._save_progress(run_id, counts)

        await self._bounded([partial(one, i) for i in meter_ids], self._concurrency)
        logger.info("readings: %s", counts)

    async def _save_progress(self, run_id: int, counts: dict[str, int]) -> None:
        """Best-effort: a failed progress write must not fail a run whose data is fine."""
        try:
            async with self._store.transaction() as repos:
                await repos.runs.update_counts(run_id, dict(counts))
        except Exception:
            logger.warning("could not save progress for sync %d", run_id, exc_info=True)

    # -- helpers -----------------------------------------------------------------------------

    @staticmethod
    async def _bounded[T](jobs: Sequence[Callable[[], Awaitable[T]]], limit: int) -> list[T]:
        """Run jobs with at most `limit` in flight; the first failure cancels the rest.

        Each coroutine is created only once it holds a slot, so none is left unawaited.
        """
        gate = asyncio.Semaphore(limit)

        async def guarded(job: Callable[[], Awaitable[T]]) -> T:
            async with gate:
                return await job()

        try:
            async with asyncio.TaskGroup() as group:
                tasks = [group.create_task(guarded(j)) for j in jobs]
        except BaseExceptionGroup as group_exc:
            raise group_exc.exceptions[0] from None
        return [t.result() for t in tasks]

    async def _finish(
        self,
        run_id: int,
        status: SyncStatus,
        strategy: SyncStrategy | None,
        counts: dict[str, int],
        error: str | None,
    ) -> None:
        async with self._store.transaction() as repos:
            await repos.runs.finish_run(
                run_id,
                status=status,
                strategy=strategy,
                finished_at=self._clock.now(),
                counts=counts,
                error=error,
            )

    async def _finish_quietly(
        self, run_id: int, strategy: SyncStrategy | None, counts: dict[str, int], error: str
    ) -> None:
        try:
            await self._finish(run_id, SyncStatus.FAILED, strategy, counts, error)
        except Exception:
            logger.error("could not record the end of sync %d", run_id, exc_info=True)


async def all_pages[T](fetch: Callable[[int], Awaitable[PortalPage[T]]]) -> list[T]:
    """Collect every page: stop on a short or empty page, or once `total` items are in."""
    items: list[T] = []
    page = 1
    while True:
        result = await fetch(page)
        items.extend(result.items)
        if len(result.items) < result.page_size or not result.items or len(items) >= result.total:
            return items
        page += 1


def _expected(exc: Exception) -> bool:
    return isinstance(exc, DomainError | _Abort)


def _describe(exc: Exception) -> str:
    if isinstance(exc, _Abort):
        return str(exc)
    if isinstance(exc, DomainError):
        return f"{type(exc).__name__}: {exc.message}"
    return type(exc).__name__


def _unique_by_id(meters: list[Meter]) -> list[Meter]:
    """Keep the first meter for each id; a repeated id would be counted but stored once."""
    first: dict[str, Meter] = {}
    for m in meters:
        first.setdefault(m.meter_id, m)
    unique = list(first.values())
    if len(unique) != len(meters):
        logger.warning(
            "portal returned %d duplicate meter ids; keeping the first", len(meters) - len(unique)
        )
    return unique
