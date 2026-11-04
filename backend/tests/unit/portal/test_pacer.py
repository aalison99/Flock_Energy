import asyncio
from collections.abc import Callable
from datetime import UTC, datetime

import httpx
import pytest

from app.portal.pacer import RequestPacer
from app.portal.parsers.registry import PayloadKind, default_registry
from app.portal.secret import Secret
from app.portal.session import PortalCredentials, PortalSession
from tests.support.fake_clock import FakeClock, FakeSleeper
from tests.support.portal_emulator import PortalEmulator

pytestmark = pytest.mark.anyio
T0 = datetime(2026, 11, 4, tzinfo=UTC)


def mono(clock: FakeClock) -> Callable[[], float]:
    return lambda: (clock.now() - T0).total_seconds()


def make(rps: float = 4.0) -> tuple[RequestPacer, FakeClock, FakeSleeper]:
    clock = FakeClock(T0)
    sleeper = FakeSleeper(clock)
    return RequestPacer(max_rps=rps, monotonic=mono(clock), sleep=sleeper), clock, sleeper


async def test_first_acquire_does_not_wait() -> None:
    pacer, _, sleeper = make()
    await pacer.acquire()
    assert sleeper.delays == []


async def test_concurrent_acquires_start_a_quarter_second_apart() -> None:
    pacer, clock, _ = make(4.0)
    starts: list[float] = []

    async def one() -> None:
        await pacer.acquire()
        starts.append((clock.now() - T0).total_seconds())

    await asyncio.gather(*(one() for _ in range(5)))
    assert starts == [0.0, 0.25, 0.5, 0.75, 1.0]


async def test_idle_time_gives_no_catch_up_burst() -> None:
    pacer, clock, sleeper = make(4.0)
    await pacer.acquire()
    clock.advance(60)  # long idle
    await pacer.acquire()  # immediate
    assert sleeper.delays == []
    await pacer.acquire()  # but the next one is spaced again
    assert sleeper.delays == [0.25]


async def test_session_paces_every_http_request_including_login() -> None:
    emulator = PortalEmulator()
    clock = FakeClock(T0)
    sleeper = FakeSleeper(clock)
    pacer = RequestPacer(max_rps=4.0, monotonic=mono(clock), sleep=sleeper)
    requests: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        return emulator.handle(request)

    session = PortalSession(
        "https://portal.example.test",
        PortalCredentials("tester@example.test", Secret(emulator.password)),
        timeout_s=5,
        transport=httpx.MockTransport(handle),
        pacer=pacer,
    )
    parsers = default_registry()
    for _ in range(3):
        await session.request(
            "GET",
            "/portal/meters/J100000/geo",
            parse=lambda r: parsers.parse(PayloadKind.GEO, r.content),
        )
    assert requests[0] == "/login"
    assert len(requests) == 4  # login + 3 data calls
    assert len(sleeper.delays) == 3  # the first request is free, the other three are spaced
    assert sleeper.delays == [0.25, 0.25, 0.25]
    n = len(requests)
    await session.aclose()  # sign-out is best-effort and not paced
    assert len(sleeper.delays) == 3
    assert len(requests) == n + 1


async def test_pacing_holds_when_the_sleeper_yields_to_other_callers() -> None:
    """A sleeper that yields lets every waiter run; only the lock keeps starts spaced."""
    clock = FakeClock(T0)
    inner = FakeSleeper(clock)

    async def yielding(delay: float) -> None:
        await asyncio.sleep(0)
        await inner(delay)
        await asyncio.sleep(0)

    pacer = RequestPacer(max_rps=2.0, monotonic=mono(clock), sleep=yielding)
    starts: list[float] = []

    async def one() -> None:
        await pacer.acquire()
        starts.append(mono(clock)())

    await asyncio.gather(*(one() for _ in range(6)))
    assert starts == [0.0, 0.5, 1.0, 1.5, 2.0, 2.5]
