"""CachingClient: TTL cache with stale-on-error around any PortalClient.

Known limit: no single-flight de-duplication; concurrent misses for the same key each call
the inner client. Values cached are immutable (frozen dataclasses, tuples) or copied lists.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from typing import cast

from app.core.interfaces import Cache, Clock
from app.domain.exceptions import UpstreamUnavailableError
from app.domain.models import GeoPoint, Meter, Reading, Transformer
from app.portal.interfaces import Freshness, PortalClient, PortalPage, cache_key, normalise_query

logger = logging.getLogger(__name__)

_READINGS = "get_readings"


@dataclass(frozen=True)
class TtlPolicy:
    static_s: float  # meters, detail, geo, transformers
    readings_s: float


class CachingClient:
    """Implements PortalClient and FreshnessReader; bulk_export and aclose are not cached."""

    def __init__(self, inner: PortalClient, *, cache: Cache, ttls: TtlPolicy, clock: Clock) -> None:
        self._inner = inner
        self._cache = cache
        self._ttls = ttls
        self._clock = clock

    def freshness(self, method: str, *args: object) -> Freshness | None:
        entry = self._cache.peek(cache_key(method, *args))
        if entry is None:
            return None
        return Freshness(entry.stored_at, entry.expires_at, self._clock.now() > entry.expires_at)

    async def _cached[T](
        self, method: str, args: tuple[object, ...], call: Callable[[], Awaitable[T]]
    ) -> T:
        key = cache_key(method, *args)
        entry = self._cache.get(key)
        if entry is not None and self._clock.now() <= entry.expires_at:
            return cast(T, _copy(entry.value))
        try:
            value = await call()
        except UpstreamUnavailableError:
            if entry is None:
                raise
            logger.warning("serving stale %s", method)
            return cast(T, _copy(entry.value))
        ttl = self._ttls.readings_s if method == _READINGS else self._ttls.static_s
        self._cache.set(key, value, ttl)
        return _copy(value)

    async def list_meters(self, page: int, query: str | None = None) -> PortalPage[Meter]:
        q = normalise_query(query)  # the key and the portal call use the same value
        return await self._cached(
            "list_meters", (page, q), lambda: self._inner.list_meters(page, q)
        )

    async def get_meter(self, meter_id: str) -> Meter:
        return await self._cached("get_meter", (meter_id,), lambda: self._inner.get_meter(meter_id))

    async def get_geo(self, meter_id: str) -> GeoPoint | None:
        return await self._cached("get_geo", (meter_id,), lambda: self._inner.get_geo(meter_id))

    async def get_readings(
        self, meter_id: str, start: date | None = None, end: date | None = None
    ) -> list[Reading]:
        return await self._cached(
            _READINGS,
            (meter_id, start, end),
            lambda: self._inner.get_readings(meter_id, start, end),
        )

    async def list_transformers(self, page: int) -> PortalPage[Transformer]:
        return await self._cached(
            "list_transformers", (page,), lambda: self._inner.list_transformers(page)
        )

    async def bulk_export(self) -> list[Meter]:
        return await self._inner.bulk_export()

    async def aclose(self) -> None:
        await self._inner.aclose()


def _copy[T](value: T) -> T:
    return cast(T, list(value)) if isinstance(value, list) else value
