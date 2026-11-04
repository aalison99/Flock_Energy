"""RequestPacer: spaces the start of portal requests so bursts never reach the rate limit."""

import asyncio
import time
from collections.abc import Awaitable, Callable


class RequestPacer:
    """Remembers the earliest instant the next request may start; callers queue on a lock.

    Each `acquire` waits until that instant, then moves it `1/max_rps` seconds on, so starts
    are evenly spaced across all concurrent callers and an idle spell earns no burst.
    Time comes from a monotonic source, so wall-clock jumps cannot stall or flood it.
    """

    def __init__(
        self,
        *,
        max_rps: float,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if max_rps <= 0:
            raise ValueError("max_rps must be positive")
        self._interval = 1.0 / max_rps
        self._monotonic = monotonic
        self._sleep = sleep
        self._lock = asyncio.Lock()
        self._next: float | None = None

    async def acquire(self) -> None:
        async with self._lock:
            now = self._monotonic()
            start = now if self._next is None or self._next <= now else self._next
            if start > now:
                await self._sleep(start - now)
            self._next = start + self._interval
