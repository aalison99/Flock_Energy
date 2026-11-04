from datetime import UTC, datetime

import httpx
import pytest

from app.core.cache import InMemoryTTLCache
from app.portal.breaker import BreakerState
from app.portal.caching import CachingClient, TtlPolicy
from app.portal.factory import PortalStack, build_portal_stack
from app.portal.http_client import HttpPortalClient
from app.portal.retrying import RetryingClient, RetryPolicy
from tests.support.fake_clock import FakeClock, no_sleep
from tests.support.portal_emulator import PortalEmulator


class Built:
    def __init__(self) -> None:
        self.requests: list[str] = []
        self.emulator = PortalEmulator()
        clock = FakeClock(datetime(2026, 11, 4, tzinfo=UTC))
        self.stack: PortalStack = build_portal_stack(
            base_url="https://portal.example.test",
            email="tester@example.test",
            password=self.emulator.password,
            timeout_s=5,
            retry=RetryPolicy(3, 0.01, 0.02, 1.0),
            breaker_threshold=5,
            breaker_reset_s=30,
            ttls=TtlPolicy(100, 10),
            cache=InMemoryTTLCache(clock, 10),
            clock=clock,
            max_rps=1000,
            sleep=no_sleep,
            transport=httpx.MockTransport(self._handle),
        )

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request.url.path)
        return self.emulator.handle(request)


@pytest.fixture
def built() -> Built:
    return Built()


def test_nesting_order(built: Built) -> None:
    # Private attributes are inspected on purpose: nesting order is the thing under test.
    assert isinstance(built.stack.client, CachingClient)
    retrying = built.stack.client._inner
    assert isinstance(retrying, RetryingClient)
    assert isinstance(retrying._inner, HttpPortalClient)


def test_stack_exposes_the_caching_client_and_a_closed_breaker(built: Built) -> None:
    assert built.stack.freshness is built.stack.client
    assert built.stack.breaker.state is BreakerState.CLOSED


def test_building_makes_no_requests(built: Built) -> None:
    assert built.requests == []


@pytest.mark.anyio
async def test_stack_works_end_to_end_and_caches(built: Built) -> None:
    await built.stack.client.get_meter("J100000")
    seen = len(built.requests)
    assert seen > 0
    await built.stack.client.get_meter("J100000")
    assert len(built.requests) == seen
    assert built.stack.freshness.freshness("get_meter", "J100000") is not None
    await built.stack.client.aclose()
