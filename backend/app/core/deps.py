"""Composition root: the only place concrete classes are wired into the app.

Tests swap implementations through `app.dependency_overrides`.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Request

from app.core.cache import InMemoryTTLCache
from app.core.clock import SystemClock
from app.core.config import Settings
from app.core.interfaces import Clock
from app.portal.caching import TtlPolicy
from app.portal.factory import build_portal_stack
from app.portal.interfaces import BreakerStateReader, FreshnessReader, PortalClient
from app.portal.retrying import RetryPolicy
from app.services.catalogs.live_catalog import LiveMeterCatalog
from app.services.health_service import HealthService
from app.services.interfaces import MeterCatalog
from app.services.meter_service import MeterService
from app.services.transformer_service import TransformerService


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
    )
    app.state.settings = settings
    app.state.clock = clock
    app.state.portal = stack.client
    app.state.freshness = stack.freshness
    app.state.breaker = stack.breaker


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Nothing to start (the portal session logs in lazily); close the portal on shutdown."""
    try:
        yield
    finally:
        await app.state.portal.aclose()


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


def get_meter_catalog(portal: Annotated[PortalClient, Depends(get_portal)]) -> MeterCatalog:
    # M6: swap this one line for the local-index catalog.
    return LiveMeterCatalog(portal)


def get_meter_service(
    catalog: Annotated[MeterCatalog, Depends(get_meter_catalog)],
    portal: Annotated[PortalClient, Depends(get_portal)],
    freshness: Annotated[FreshnessReader, Depends(get_freshness)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> MeterService:
    return MeterService(catalog, portal, freshness, clock)


def get_transformer_service(
    portal: Annotated[PortalClient, Depends(get_portal)],
) -> TransformerService:
    return TransformerService(portal)


def get_health_service(
    breaker: Annotated[BreakerStateReader, Depends(get_breaker_state)],
) -> HealthService:
    return HealthService(breaker)
