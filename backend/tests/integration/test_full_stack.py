"""End to end through the real client stack (cache, retry, HTTP) over the portal emulator."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.cache import InMemoryTTLCache
from app.core.config import Settings
from app.core.deps import get_breaker_state, get_freshness, get_portal, get_task_runner
from app.main import create_app
from app.portal.caching import TtlPolicy
from app.portal.factory import build_portal_stack
from app.portal.retrying import RetryPolicy
from tests.support.fake_clock import FakeClock, no_sleep
from tests.support.portal_emulator import PortalEmulator
from tests.support.tasks import ManualTaskRunner

STATIC_TTL_S = 86400
READINGS_TTL_S = 900


@dataclass
class Stack:
    client: TestClient
    emulator: PortalEmulator
    clock: FakeClock


@pytest.fixture
def stack(settings: Settings) -> Iterator[Stack]:
    emulator = PortalEmulator()
    clock = FakeClock(datetime(2026, 11, 4, tzinfo=UTC))
    built = build_portal_stack(
        base_url="https://portal.example.test",
        email="tester@example.test",
        password=emulator.password,
        timeout_s=5,
        retry=RetryPolicy(2, 0.001, 0.002, 1.0),
        breaker_threshold=50,
        breaker_reset_s=30,
        ttls=TtlPolicy(STATIC_TTL_S, 900),
        cache=InMemoryTTLCache(clock, 1000),
        clock=clock,
        max_rps=1000,
        sleep=no_sleep,
        transport=httpx.MockTransport(emulator.handle),
    )
    app = create_app(settings)
    app.dependency_overrides[get_portal] = lambda: built.client
    app.dependency_overrides[get_freshness] = lambda: built.freshness
    app.dependency_overrides[get_breaker_state] = lambda: built.breaker
    with TestClient(app, raise_server_exceptions=False) as client:
        yield Stack(client, emulator, clock)


def test_meter_detail_real_values_then_cache(stack: Stack) -> None:
    r = stack.client.get("/api/v1/meters/J100000")
    assert r.status_code == 200
    body = r.json()
    assert body["serial_no"] == "SE33962"
    assert body["hierarchy"][-1] == {"level": "dt", "code": "DT-001", "name": "Malviya Nagar DT 1"}
    assert body["geo"] == {"lat": 26.938961002479868, "lng": 75.83095696146852}
    assert body["meta"]["stale"] is False
    assert body["meta"]["fetched_at"].startswith("2026-11-04T00:00:00")
    seen = len(stack.emulator.requests)
    assert seen > 0
    again = stack.client.get("/api/v1/meters/J100000")
    assert again.status_code == 200
    assert len(stack.emulator.requests) == seen


def test_search_through_the_stack(stack: Stack) -> None:
    r = stack.client.get("/api/v1/meters?q=se33962")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["meter_id"] == "J100000"


def test_stale_on_error(stack: Stack) -> None:
    assert stack.client.get("/api/v1/meters/J100000").status_code == 200
    stack.emulator.fail_next(50, status=503)

    fresh = stack.client.get("/api/v1/meters/J100000")
    assert fresh.status_code == 200
    assert fresh.json()["meta"]["stale"] is False

    stack.clock.advance(STATIC_TTL_S + 1)
    stale = stack.client.get("/api/v1/meters/J100000")
    assert stale.status_code == 200
    assert stale.json()["meta"]["stale"] is True
    assert stale.json()["serial_no"] == "SE33962"


def test_uncached_meter_with_portal_down_is_503(stack: Stack) -> None:
    stack.emulator.fail_next(50, status=503)
    r = stack.client.get("/api/v1/meters/J100000")
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "upstream_unavailable"


def test_readings_cached_then_stale_on_error(stack: Stack) -> None:
    url = "/api/v1/meters/J100000/readings?start=2026-06-29&end=2026-06-30"
    first = stack.client.get(url)
    assert first.status_code == 200
    assert len(first.json()["points"]) == 96
    seen = len(stack.emulator.requests)
    assert seen > 0

    again = stack.client.get(url)
    assert again.status_code == 200
    assert len(stack.emulator.requests) == seen  # served from cache, no emulator hit

    stack.emulator.fail_next(50, status=503)
    stack.clock.advance(READINGS_TTL_S + 1)
    stale = stack.client.get(url)
    assert stale.status_code == 200
    assert stale.json()["meta"]["stale"] is True
    assert len(stale.json()["points"]) == 96


def test_uncached_readings_with_portal_down_is_503(stack: Stack) -> None:
    stack.emulator.fail_next(50, status=503)
    assert stack.client.get("/api/v1/meters/J100000/readings").status_code == 503


def test_sync_through_the_real_stack_fills_the_index_via_the_signed_export(
    settings: Settings,
) -> None:
    emulator = PortalEmulator()
    clock = FakeClock(datetime(2026, 11, 4, tzinfo=UTC))
    built = build_portal_stack(
        base_url="https://portal.example.test",
        email="tester@example.test",
        password=emulator.password,
        timeout_s=5,
        retry=RetryPolicy(2, 0.001, 0.002, 1.0),
        breaker_threshold=50,
        breaker_reset_s=30,
        ttls=TtlPolicy(STATIC_TTL_S, 900),
        cache=InMemoryTTLCache(clock, 1000),
        clock=clock,
        max_rps=1000,
        sleep=no_sleep,
        transport=httpx.MockTransport(emulator.handle),
    )
    app = create_app(settings)
    app.dependency_overrides[get_portal] = lambda: built.client
    app.dependency_overrides[get_freshness] = lambda: built.freshness
    app.dependency_overrides[get_breaker_state] = lambda: built.breaker
    tasks = ManualTaskRunner()
    app.dependency_overrides[get_task_runner] = lambda: tasks
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.post("/api/v1/sync", json={"include_readings": False}).status_code == 202
        client.portal.call(tasks.run_all)  # type: ignore[union-attr]
        latest = client.get("/api/v1/sync/status").json()["latest"]
        assert latest["status"] == "succeeded", latest
        assert latest["strategy"] == "export"
        assert latest["counts"]["meters"] == 403
        ready = client.get("/api/v1/health/ready").json()
        assert ready["index"]["meter_count"] == 403
