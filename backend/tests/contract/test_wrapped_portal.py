"""The PortalClient contract through all three layers: caching, retrying, HTTP."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest

from app.core.cache import InMemoryTTLCache
from app.portal.caching import TtlPolicy
from app.portal.factory import build_portal_stack
from app.portal.interfaces import PortalClient
from app.portal.retrying import RetryPolicy
from tests.contract.portal_contract import PortalClientContract
from tests.support.fake_clock import FakeClock, no_sleep
from tests.support.portal_emulator import PortalEmulator


class TestWrappedPortal(PortalClientContract):
    @pytest.fixture
    async def portal(self) -> AsyncIterator[PortalClient]:
        emulator = PortalEmulator()
        clock = FakeClock(datetime(2026, 11, 4, tzinfo=UTC))
        stack = build_portal_stack(
            base_url="https://portal.example.test",
            email="tester@example.test",
            password=emulator.password,
            timeout_s=5,
            retry=RetryPolicy(3, 0.01, 0.02, 1.0),
            breaker_threshold=5,
            breaker_reset_s=30,
            ttls=TtlPolicy(86400, 900),
            cache=InMemoryTTLCache(clock, 1000),
            clock=clock,
            max_rps=1000,
            sleep=no_sleep,
            transport=httpx.MockTransport(emulator.handle),
        )
        yield stack.client
        await stack.client.aclose()
