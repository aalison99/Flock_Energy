"""RetryingClient: backoff with jitter plus a circuit breaker around any PortalClient."""

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date

from app.domain.exceptions import (
    NotFoundError,
    UpstreamAuthError,
    UpstreamProtocolError,
    UpstreamUnavailableError,
    ValidationError,
)
from app.domain.models import GeoPoint, Meter, Reading, Transformer
from app.portal.breaker import CircuitBreaker
from app.portal.interfaces import PortalClient, PortalPage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int  # total attempts, including the first
    base_delay_s: float
    max_delay_s: float
    retry_after_cap_s: float  # a longer Retry-After than this is not waited for


class RetryingClient:
    """Implements PortalClient; retries only UpstreamUnavailableError.

    Auth errors count toward the breaker but are never retried. Answers from the portal
    (not found, protocol, validation) prove it is up, so they count as breaker successes.
    """

    def __init__(
        self,
        inner: PortalClient,
        *,
        policy: RetryPolicy,
        breaker: CircuitBreaker,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        self._inner = inner
        self._policy = policy
        self._breaker = breaker
        self._sleep = sleep
        self._jitter = jitter

    async def _run[T](self, name: str, call: Callable[[], Awaitable[T]]) -> T:
        policy = self._policy
        attempt = 1
        while True:
            permit = self._breaker.before_call()
            try:
                result = await call()
            except UpstreamUnavailableError as exc:
                self._breaker.record_failure(permit)
                if attempt >= policy.attempts:
                    raise
                delay = self._delay(attempt + 1, exc.retry_after_s)
                if delay is None:
                    raise
                attempt += 1
                logger.warning(
                    "portal call %s failed (%s); retry %d/%d in %.2fs",
                    name,
                    type(exc).__name__,
                    attempt - 1,
                    policy.attempts - 1,
                    delay,
                )
                await self._sleep(delay)
            except UpstreamAuthError:
                self._breaker.record_failure(permit)
                raise
            except asyncio.CancelledError:
                self._breaker.release_trial(permit)  # not the portal's fault: free the trial slot
                raise
            except (NotFoundError, UpstreamProtocolError, ValidationError):
                self._breaker.record_success(permit)
                raise
            except Exception:
                self._breaker.record_failure(permit)  # unexpected: a failed trial, never a wedge
                raise
            else:
                self._breaker.record_success(permit)
                return result

    def _delay(self, attempt: int, retry_after_s: int | None) -> float | None:
        """Seconds to wait before `attempt` (>= 2), or None when waiting is not worth it."""
        policy = self._policy
        if retry_after_s is not None:
            return None if retry_after_s > policy.retry_after_cap_s else float(retry_after_s)
        step: float = min(policy.max_delay_s, policy.base_delay_s * 2.0 ** (attempt - 2))
        return step * (0.5 + self._jitter() / 2)

    async def list_meters(self, page: int, query: str | None = None) -> PortalPage[Meter]:
        return await self._run("list_meters", lambda: self._inner.list_meters(page, query))

    async def get_meter(self, meter_id: str) -> Meter:
        return await self._run("get_meter", lambda: self._inner.get_meter(meter_id))

    async def get_geo(self, meter_id: str) -> GeoPoint | None:
        return await self._run("get_geo", lambda: self._inner.get_geo(meter_id))

    async def get_readings(
        self, meter_id: str, start: date | None = None, end: date | None = None
    ) -> list[Reading]:
        return await self._run(
            "get_readings", lambda: self._inner.get_readings(meter_id, start, end)
        )

    async def list_transformers(self, page: int) -> PortalPage[Transformer]:
        return await self._run("list_transformers", lambda: self._inner.list_transformers(page))

    async def bulk_export(self) -> list[Meter]:
        return await self._run("bulk_export", self._inner.bulk_export)

    async def aclose(self) -> None:
        await self._inner.aclose()
