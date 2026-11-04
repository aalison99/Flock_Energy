"""Composition root: the only place concrete classes are wired into the app.

Tests swap implementations through `app.dependency_overrides`.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.core.cache import InMemoryTTLCache
from app.core.clock import SystemClock
from app.core.config import Settings
from app.core.interfaces import Clock, TaskRunner
from app.core.tasks import AsyncioTaskRunner
from app.db.engine import make_async_engine, run_migrations
from app.domain.exceptions import ConflictError
from app.portal.caching import TtlPolicy
from app.portal.factory import build_portal_stack
from app.portal.interfaces import BreakerStateReader, FreshnessReader, PortalClient
from app.portal.retrying import RetryPolicy
from app.repositories.interfaces import (
    IndexStore,
    MeterRepository,
    ReadingRepository,
    SyncRepository,
    TransformerRepository,
)
from app.repositories.sqlite.meter_repo import SqliteMeterRepository
from app.repositories.sqlite.reading_repo import SqliteReadingRepository
from app.repositories.sqlite.store import SqliteIndexStore
from app.repositories.sqlite.sync_repo import SqliteSyncRepository
from app.repositories.sqlite.transformer_repo import SqliteTransformerRepository
from app.services.catalogs.indexed_catalog import IndexedMeterCatalog
from app.services.catalogs.live_catalog import LiveMeterCatalog
from app.services.catalogs.prefer_index import PreferIndexCatalog
from app.services.data_quality_service import DataQualityService
from app.services.geo_service import GeoService
from app.services.health_service import HealthService
from app.services.hierarchy_service import HierarchyService
from app.services.interfaces import IndexStatusReader, MeterCatalog
from app.services.meter_service import MeterService
from app.services.quality.registry import CHECKS
from app.services.reading_service import ReadingService
from app.services.sync_service import SyncService
from app.services.transformer_service import TransformerService

logger = logging.getLogger("urja.startup")


def wire(app: FastAPI, settings: Settings) -> None:
    """Attach settings and concrete collaborators to the app state (no network calls)."""
    clock = SystemClock()
    stack = build_portal_stack(
        base_url=str(settings.portal_url).rstrip("/"),
        email=settings.portal_email,
        password=settings.portal_password.get_secret_value(),
        timeout_s=settings.http_timeout_s,
        retry=RetryPolicy(
            attempts=settings.retry_attempts,
            base_delay_s=settings.retry_base_delay_s,
            max_delay_s=settings.retry_max_delay_s,
            retry_after_cap_s=settings.retry_after_cap_s,
        ),
        breaker_threshold=settings.breaker_failure_threshold,
        breaker_reset_s=settings.breaker_reset_s,
        ttls=TtlPolicy(static_s=settings.ttl_static_s, readings_s=settings.ttl_readings_s),
        cache=InMemoryTTLCache(clock, settings.cache_max_entries),
        clock=clock,
        max_rps=settings.portal_max_rps,
    )
    app.state.settings = settings
    app.state.clock = clock
    app.state.portal = stack.client
    app.state.freshness = stack.freshness
    app.state.breaker = stack.breaker
    app.state.db_engine = make_async_engine(settings.db_url)  # lazy: no file I/O until first use
    app.state.tasks = AsyncioTaskRunner()


def build_sync_service(
    portal: PortalClient,
    store: IndexStore,
    tasks: TaskRunner,
    clock: Clock,
    settings: Settings,
) -> SyncService:
    """The one place a SyncService is assembled (request provider and startup both use it)."""
    return SyncService(portal, store, tasks, clock, concurrency=settings.sync_concurrency)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Migrate, fail leftover runs, start a sync if the index is empty; on shutdown stop tasks,
    then close the portal, then the DB."""
    settings: Settings = app.state.settings
    engine: AsyncEngine = app.state.db_engine
    try:
        if settings.db_migrate_on_startup:
            await asyncio.to_thread(run_migrations, settings.db_url)
        async with engine.begin() as conn:
            await SqliteSyncRepository(conn).fail_stale_runs(
                app.state.clock.now(), "interrupted: process restarted"
            )
        if settings.sync_on_startup:
            service = build_sync_service(
                app.state.portal,
                SqliteIndexStore(engine),
                app.state.tasks,
                app.state.clock,
                settings,
            )
            await _sync_if_index_empty(service, settings)
        yield
    finally:
        try:
            await app.state.tasks.aclose()
        finally:
            try:
                await app.state.portal.aclose()
            finally:
                await engine.dispose()


async def _sync_if_index_empty(service: SyncService, settings: Settings) -> None:
    """The run itself is a background task, so startup makes no portal request."""
    if (await service.index_info()).ready:
        return
    try:
        await service.start(include_readings=settings.sync_readings_on_startup)
    except ConflictError:
        logger.warning("startup sync skipped: a sync is already running")


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_clock(request: Request) -> Clock:
    clock: Clock = request.app.state.clock
    return clock


def get_portal(request: Request) -> PortalClient:
    portal: PortalClient = request.app.state.portal
    return portal


def get_freshness(request: Request) -> FreshnessReader:
    freshness: FreshnessReader = request.app.state.freshness
    return freshness


def get_breaker_state(request: Request) -> BreakerStateReader:
    breaker: BreakerStateReader = request.app.state.breaker
    return breaker


async def get_db_connection(request: Request) -> AsyncIterator[AsyncConnection]:
    """One transaction per request: commit on success, roll back on error.

    Used with scope="function" so the commit happens before the response is sent.
    """
    engine: AsyncEngine = request.app.state.db_engine
    async with engine.begin() as conn:
        yield conn


def get_meter_repository(
    conn: Annotated[AsyncConnection, Depends(get_db_connection, scope="function")],
) -> MeterRepository:
    return SqliteMeterRepository(conn)


def get_meter_catalog(
    repo: Annotated[MeterRepository, Depends(get_meter_repository)],
    portal: Annotated[PortalClient, Depends(get_portal)],
) -> MeterCatalog:
    # The one line that picks the catalog: the index, falling back to the live portal.
    return PreferIndexCatalog(IndexedMeterCatalog(repo), LiveMeterCatalog(portal))


def get_meter_service(
    catalog: Annotated[MeterCatalog, Depends(get_meter_catalog)],
    portal: Annotated[PortalClient, Depends(get_portal)],
    freshness: Annotated[FreshnessReader, Depends(get_freshness)],
    clock: Annotated[Clock, Depends(get_clock)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MeterService:
    return MeterService(catalog, portal, freshness, clock, settings.index_max_age_s)


def get_geo_service(
    repo: Annotated[MeterRepository, Depends(get_meter_repository)],
) -> GeoService:
    return GeoService(repo)


def get_reading_service(
    portal: Annotated[PortalClient, Depends(get_portal)],
    freshness: Annotated[FreshnessReader, Depends(get_freshness)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> ReadingService:
    return ReadingService(portal, freshness, clock)


def get_transformer_service(
    portal: Annotated[PortalClient, Depends(get_portal)],
    catalog: Annotated[MeterCatalog, Depends(get_meter_catalog)],
) -> TransformerService:
    return TransformerService(portal, catalog)


def get_index_store(request: Request) -> IndexStore:
    return SqliteIndexStore(request.app.state.db_engine)


def get_task_runner(request: Request) -> TaskRunner:
    tasks: TaskRunner = request.app.state.tasks
    return tasks


def get_sync_service(
    portal: Annotated[PortalClient, Depends(get_portal)],
    store: Annotated[IndexStore, Depends(get_index_store)],
    tasks: Annotated[TaskRunner, Depends(get_task_runner)],
    clock: Annotated[Clock, Depends(get_clock)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> SyncService:
    return build_sync_service(portal, store, tasks, clock, settings)


def get_health_service(
    breaker: Annotated[BreakerStateReader, Depends(get_breaker_state)],
    index: Annotated[IndexStatusReader, Depends(get_sync_service)],
) -> HealthService:
    return HealthService(breaker, index)


def get_transformer_repository(
    conn: Annotated[AsyncConnection, Depends(get_db_connection, scope="function")],
) -> TransformerRepository:
    return SqliteTransformerRepository(conn)


def get_reading_repository(
    conn: Annotated[AsyncConnection, Depends(get_db_connection, scope="function")],
) -> ReadingRepository:
    return SqliteReadingRepository(conn)


def get_sync_repository(
    conn: Annotated[AsyncConnection, Depends(get_db_connection, scope="function")],
) -> SyncRepository:
    return SqliteSyncRepository(conn)


def get_hierarchy_service(
    meters: Annotated[MeterRepository, Depends(get_meter_repository)],
    transformers: Annotated[TransformerRepository, Depends(get_transformer_repository)],
) -> HierarchyService:
    return HierarchyService(meters, transformers)


def get_data_quality_service(
    meters: Annotated[MeterRepository, Depends(get_meter_repository)],
    transformers: Annotated[TransformerRepository, Depends(get_transformer_repository)],
) -> DataQualityService:
    # The one line that picks the checks: everything in the registry.
    return DataQualityService(CHECKS, meters, transformers)
