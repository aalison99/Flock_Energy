"""Fixtures for API tests: the real app with fake portal collaborators swapped in."""

from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.deps import get_breaker_state, get_freshness, get_portal, get_task_runner
from app.main import create_app
from app.portal.fake import FakePortalClient
from tests.support.fakes import FakeBreaker, FakeFreshness
from tests.support.portal_emulator import FIXTURES
from tests.support.tasks import ManualTaskRunner


@dataclass
class Api:
    app: FastAPI
    client: TestClient
    portal: FakePortalClient
    freshness: FakeFreshness
    breaker: FakeBreaker
    tasks: ManualTaskRunner


@pytest.fixture
def api(settings: Settings) -> Iterator[Api]:
    app = create_app(settings)
    portal = FakePortalClient(FIXTURES)
    freshness = FakeFreshness()
    breaker = FakeBreaker()
    tasks = ManualTaskRunner()
    app.dependency_overrides[get_task_runner] = lambda: tasks
    app.dependency_overrides[get_portal] = lambda: portal
    app.dependency_overrides[get_freshness] = lambda: freshness
    app.dependency_overrides[get_breaker_state] = lambda: breaker
    with TestClient(app, raise_server_exceptions=False) as client:
        yield Api(app, client, portal, freshness, breaker, tasks)
        tasks.discard()


@pytest.fixture
def synced_api(api: Api) -> Api:
    """The same app after a real SyncService run filled the index from the fixture portal."""
    assert api.client.post("/api/v1/sync", json={"include_readings": False}).status_code == 202
    api.client.portal.call(api.tasks.run_all)  # type: ignore[union-attr]
    latest = api.client.get("/api/v1/sync/status").json()["latest"]
    assert (latest["status"], latest["counts"]["meters"]) == ("succeeded", 403)
    api.portal.calls.clear()
    return api
