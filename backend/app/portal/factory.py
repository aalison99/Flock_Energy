"""Builds the portal client stack: Caching(Retrying(Http(Session))); primitives only."""

from dataclasses import dataclass

import httpx

from app.core.interfaces import Cache, Clock
from app.portal.breaker import CircuitBreaker
from app.portal.caching import CachingClient, TtlPolicy
from app.portal.http_client import HttpPortalClient
from app.portal.interfaces import BreakerStateReader, FreshnessReader, PortalClient
from app.portal.parsers.registry import default_registry
from app.portal.retrying import RetryingClient, RetryPolicy
from app.portal.secret import Secret
from app.portal.session import PortalCredentials, PortalSession
from app.portal.signer import HmacSha256Signer


@dataclass(frozen=True)
class PortalStack:
    client: PortalClient
    freshness: FreshnessReader
    breaker: BreakerStateReader


def build_portal_stack(
    *,
    base_url: str,
    email: str,
    password: str,
    timeout_s: float,
    retry: RetryPolicy,
    breaker_threshold: int,
    breaker_reset_s: float,
    ttls: TtlPolicy,
    cache: Cache,
    clock: Clock,
    transport: httpx.AsyncBaseTransport | None = None,
) -> PortalStack:
    """Wire the portal client stack; makes no network calls (the session logs in lazily)."""
    session = PortalSession(
        base_url,
        PortalCredentials(email, Secret(password)),
        timeout_s=timeout_s,
        transport=transport,
    )
    http = HttpPortalClient(session, default_registry(), HmacSha256Signer(), clock)
    breaker = CircuitBreaker(
        failure_threshold=breaker_threshold, reset_s=breaker_reset_s, clock=clock
    )
    retrying = RetryingClient(http, policy=retry, breaker=breaker)
    caching = CachingClient(retrying, cache=cache, ttls=ttls, clock=clock)
    return PortalStack(client=caching, freshness=caching, breaker=breaker)
