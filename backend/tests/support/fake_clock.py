"""Deterministic time for tests: a controllable clock and a sleeper that advances it."""

from datetime import datetime, timedelta


class FakeClock:
    def __init__(self, start: datetime) -> None:
        self._now = start

    def now(self) -> datetime:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += timedelta(seconds=seconds)


class FakeSleeper:
    """Awaitable stand-in for asyncio.sleep: records delays and advances the clock instead."""

    def __init__(self, clock: FakeClock | None = None) -> None:
        self._clock = clock
        self.delays: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)
        if self._clock is not None:
            self._clock.advance(delay)
