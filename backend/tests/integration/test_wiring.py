"""Composition-root wiring: no network at startup, clean shutdown, one-line test swap.

Startup/shutdown tests monkeypatch `app.core.deps.build_portal_stack` to inject a
MockTransport that counts requests; everything else is the real wiring.
"""

from pathlib import Path
from typing import Annotated, Any

import httpx
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.core import deps
from app.core.config import Settings
from app.core.deps import get_breaker_state, get_freshness, get_portal
from app.main import create_app
from app.portal.breaker import BreakerState
from app.portal.caching import CachingClient
from app.portal.factory import PortalStack
from app.portal.fake import FakePortalClient
from app.portal.interfaces import BreakerStateReader, FreshnessReader, PortalClient
from tests.support.portal_emulator import FIXTURES, PortalEmulator

FIXTURES_DIR: Path = FIXTURES


class CachingStub:
    def freshness(self, method: str, *args: object) -> None:
        return None


class BreakerStub:
    state = BreakerState.CLOSED


_FAKE = FakePortalClient(FIXTURES_DIR)


@pytest.fixture
def requests_seen(monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    seen: list[httpx.Request] = []
    emulator = PortalEmulator()
    real = deps.build_portal_stack

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return emulator.handle(request)

    def build(**kwargs: Any) -> Any:
        return real(**{**kwargs, "transport": httpx.MockTransport(handle)})

    monkeypatch.setattr(deps, "build_portal_stack", build)
    return seen


def test_wire_stores_portal_state(settings: Settings, requests_seen: list[httpx.Request]) -> None:
    app = create_app(settings)
    assert isinstance(app.state.portal, CachingClient)
    assert app.state.freshness is app.state.portal
    assert app.state.breaker.state is BreakerState.CLOSED


def test_no_requests_at_startup_or_shutdown(
    settings: Settings, requests_seen: list[httpx.Request]
) -> None:
    app = create_app(settings)
    with TestClient(app):
        pass
    assert requests_seen == []


def test_lifespan_closes_portal(settings: Settings, requests_seen: list[httpx.Request]) -> None:
    app = create_app(settings)
    closed: list[bool] = []

    class Spy:
        async def aclose(self) -> None:
            closed.append(True)

    app.state.portal = Spy()
    with TestClient(app):
        assert closed == []
    assert closed == [True]


def test_settings_reach_the_stack(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def build(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return PortalStack(client=_FAKE, freshness=CachingStub(), breaker=BreakerStub())

    monkeypatch.setattr(deps, "build_portal_stack", build)
    create_app(settings)
    assert captured["base_url"] == "https://portal.example.test"
    assert captured["password"] == "s3cret-value"
    assert captured["email"] == "tester@example.test"
    assert captured["retry"].attempts == settings.retry_attempts
    assert captured["ttls"].readings_s == settings.ttl_readings_s
    assert captured["breaker_threshold"] == settings.breaker_failure_threshold


def test_dependency_override_swaps_portal(
    settings: Settings, requests_seen: list[httpx.Request]
) -> None:
    app: FastAPI = create_app(settings)

    @app.get("/_test/who")
    async def who(portal: Annotated[PortalClient, Depends(get_portal)]) -> dict[str, str]:
        return {"type": type(portal).__name__}

    with TestClient(app) as client:
        assert client.get("/_test/who").json() == {"type": "CachingClient"}
        app.dependency_overrides[get_portal] = lambda: FakePortalClient(FIXTURES_DIR)
        assert client.get("/_test/who").json() == {"type": "FakePortalClient"}


def test_other_providers_return_state(
    settings: Settings, requests_seen: list[httpx.Request]
) -> None:
    app: FastAPI = create_app(settings)

    @app.get("/_test/state")
    async def state(
        fresh: Annotated[FreshnessReader, Depends(get_freshness)],
        breaker: Annotated[BreakerStateReader, Depends(get_breaker_state)],
    ) -> dict[str, object]:
        return {"fresh": fresh.freshness("get_meter", "J1") is None, "breaker": breaker.state}

    with TestClient(app) as client:
        assert client.get("/_test/state").json() == {"fresh": True, "breaker": "closed"}


@pytest.mark.anyio
async def test_lifespan_closes_portal_even_when_the_app_body_raises(settings: Settings) -> None:
    app = create_app(settings)
    closed: list[bool] = []

    class Spy:
        async def aclose(self) -> None:
            closed.append(True)

    app.state.portal = Spy()
    with pytest.raises(RuntimeError):
        async with deps.lifespan(app):
            raise RuntimeError("boom")
    assert closed == [True]
