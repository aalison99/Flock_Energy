"""POST /sync and GET /sync/status through the real app, service and SQLite index."""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.deps import get_breaker_state, get_freshness, get_portal, get_task_runner
from app.main import create_app
from app.portal.fake import FakePortalClient
from tests.support.fakes import FakeBreaker, FakeFreshness
from tests.support.portal_emulator import FIXTURES
from tests.support.tasks import ManualTaskRunner


@dataclass
class SyncApi:
    client: TestClient
    portal: FakePortalClient
    tasks: ManualTaskRunner

    def run_tasks(self) -> None:
        # The TestClient's own event loop, so the DB connections stay on one loop.
        self.client.portal.call(self.tasks.run_all)  # type: ignore[union-attr]


@pytest.fixture
def sync_api(settings: Settings) -> Iterator[SyncApi]:
    app = create_app(settings)
    portal = FakePortalClient(FIXTURES)
    tasks = ManualTaskRunner()
    app.dependency_overrides[get_portal] = lambda: portal
    app.dependency_overrides[get_freshness] = lambda: FakeFreshness()
    app.dependency_overrides[get_breaker_state] = lambda: FakeBreaker()
    app.dependency_overrides[get_task_runner] = lambda: tasks
    with TestClient(app, raise_server_exceptions=False) as client:
        yield SyncApi(client, portal, tasks)
        tasks.discard()


def test_status_before_any_sync_is_200_with_nulls(sync_api: SyncApi) -> None:
    r = sync_api.client.get("/api/v1/sync/status")
    assert r.status_code == 200
    assert r.json() == {"latest": None, "last_successful": None}


def test_post_returns_202_running_then_status_shows_success(sync_api: SyncApi) -> None:
    r = sync_api.client.post("/api/v1/sync")
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "running"
    assert body["finished_at"] is None
    assert body["counts"] == {}
    assert body["error"] is None

    running = sync_api.client.get("/api/v1/sync/status").json()
    assert running["latest"]["id"] == body["id"]
    assert running["last_successful"] is None

    sync_api.run_tasks()
    done: dict[str, Any] = sync_api.client.get("/api/v1/sync/status").json()
    latest = done["latest"]
    assert latest["id"] == body["id"]
    assert latest["status"] == "succeeded"
    assert latest["strategy"] == "export"
    assert latest["finished_at"] is not None
    assert latest["counts"]["meters"] == 403
    assert latest["counts"]["transformers"] == 40
    assert latest["counts"]["readings"] > 0
    assert done["last_successful"] == latest


def test_include_readings_false_is_honoured(sync_api: SyncApi) -> None:
    r = sync_api.client.post("/api/v1/sync", json={"include_readings": False})
    assert r.status_code == 202
    sync_api.run_tasks()
    latest = sync_api.client.get("/api/v1/sync/status").json()["latest"]
    assert latest["counts"]["readings"] == 0
    assert not any(c[0] == "get_readings" for c in sync_api.portal.calls)


def test_second_post_while_running_is_409(sync_api: SyncApi) -> None:
    assert sync_api.client.post("/api/v1/sync").status_code == 202
    r = sync_api.client.post("/api/v1/sync")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "conflict"
    assert set(r.json()["error"]) == {"code", "message", "details"}
    assert len(sync_api.tasks.pending) == 1


def test_post_after_completion_starts_a_new_run(sync_api: SyncApi) -> None:
    first = sync_api.client.post("/api/v1/sync").json()
    sync_api.run_tasks()
    second = sync_api.client.post("/api/v1/sync")
    assert second.status_code == 202
    assert second.json()["id"] != first["id"]


def test_bad_body_is_422(sync_api: SyncApi) -> None:
    r = sync_api.client.post("/api/v1/sync", json={"include_readings": "maybe"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"
    assert sync_api.tasks.pending == []


def test_failed_run_is_reported(sync_api: SyncApi) -> None:
    from app.domain.exceptions import UpstreamUnavailableError

    sync_api.portal.fail("list_transformers", UpstreamUnavailableError("dts down"), times=3)
    sync_api.client.post("/api/v1/sync")
    sync_api.run_tasks()
    status = sync_api.client.get("/api/v1/sync/status").json()
    assert status["latest"]["status"] == "failed"
    assert status["latest"]["error"] == "UpstreamUnavailableError: dts down"
    assert status["last_successful"] is None


def test_readiness_reports_the_index_before_and_after_sync(sync_api: SyncApi) -> None:
    before = sync_api.client.get("/api/v1/health/ready")
    assert before.status_code == 200
    assert before.json()["index"] == {"ready": False, "meter_count": 0, "last_sync_at": None}
    sync_api.client.post("/api/v1/sync")
    sync_api.run_tasks()
    after = sync_api.client.get("/api/v1/health/ready").json()
    assert after["status"] == "ready"
    assert after["index"]["ready"] is True
    assert after["index"]["meter_count"] == 403
    assert after["index"]["last_sync_at"] is not None
    assert [c for c in sync_api.portal.calls if c[0] == "aclose"] == []
