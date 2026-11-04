"""Composition-root wiring: no network at startup, clean shutdown, one-line test swap.

Startup/shutdown tests monkeypatch `app.core.deps.build_portal_stack` to inject a
MockTransport that counts requests; everything else is the real wiring.
"""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import httpx
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core import deps
from app.core.config import Settings
from app.core.deps import (
    get_breaker_state,
    get_freshness,
    get_meter_repository,
    get_portal,
    get_reading_repository,
    get_sync_repository,
    get_transformer_repository,
)
from app.db.engine import run_migrations
from app.domain.models import Meter
from app.main import create_app
from app.portal.breaker import BreakerState
from app.portal.caching import CachingClient
from app.portal.factory import PortalStack
from app.portal.fake import FakePortalClient
from app.portal.interfaces import BreakerStateReader, FreshnessReader, PortalClient
from app.repositories.interfaces import (
    MeterRepository,
    ReadingRepository,
    SyncRepository,
    TransformerRepository,
)
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


def _db_path(settings: Settings) -> Path:
    return Path(settings.db_url.removeprefix("sqlite:///"))


def test_wire_builds_engine_without_touching_disk(settings: Settings) -> None:
    app = create_app(settings)
    assert isinstance(app.state.db_engine, AsyncEngine)
    assert not _db_path(settings).exists()


def test_startup_migrates_db_with_no_portal_requests(
    settings: Settings, requests_seen: list[httpx.Request]
) -> None:
    with TestClient(create_app(settings)):
        pass
    with sqlite3.connect(_db_path(settings)) as db:
        names = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"meters", "readings", "sync_runs", "transformers"} <= names
    assert requests_seen == []


def test_flag_off_does_not_migrate(settings: Settings) -> None:
    app = create_app(settings.model_copy(update={"db_migrate_on_startup": False}))
    with pytest.raises(Exception, match="no such table"), TestClient(app):
        pass
    with sqlite3.connect(_db_path(settings)) as db:
        assert db.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone() == (
            0,
        )


def test_migration_can_be_disabled(settings: Settings) -> None:
    run_migrations(settings.db_url)
    app = create_app(settings.model_copy(update={"db_migrate_on_startup": False}))
    with TestClient(app):
        pass


def test_shutdown_disposes_engine(settings: Settings) -> None:
    app = create_app(settings)
    disposed: list[bool] = []
    real: AsyncEngine = app.state.db_engine

    class EngineSpy:
        """Delegates to the real engine, recording dispose()."""

        def begin(self) -> Any:
            return real.begin()

        async def dispose(self) -> None:
            disposed.append(True)
            await real.dispose()

    app.state.db_engine = EngineSpy()
    with TestClient(app):
        assert disposed == []
    assert disposed == [True]


def test_stale_running_row_is_failed_on_startup(settings: Settings) -> None:
    run_migrations(settings.db_url)
    with sqlite3.connect(_db_path(settings)) as db:
        db.execute(
            "INSERT INTO sync_runs (status, started_at) VALUES ('running', ?)",
            (datetime(2026, 1, 1, tzinfo=UTC).isoformat(),),
        )
    with TestClient(create_app(settings)):
        pass
    with sqlite3.connect(_db_path(settings)) as db:
        status, error, finished = db.execute(
            "SELECT status, error, finished_at FROM sync_runs"
        ).fetchone()
    assert (status, error) == ("failed", "interrupted: process restarted")
    assert finished is not None


def test_repository_providers_and_override(settings: Settings) -> None:
    app: FastAPI = create_app(settings)

    @app.get("/_test/repos")
    async def repos(
        m: Annotated[MeterRepository, Depends(get_meter_repository)],
        t: Annotated[TransformerRepository, Depends(get_transformer_repository)],
        r: Annotated[ReadingRepository, Depends(get_reading_repository)],
        s: Annotated[SyncRepository, Depends(get_sync_repository)],
    ) -> dict[str, str]:
        return {type(x).__name__: "ok" for x in (m, t, r, s)}

    class FakeMeters:
        pass

    @app.get("/_test/meter-repo")
    async def meter_repo(
        m: Annotated[MeterRepository, Depends(get_meter_repository)],
    ) -> dict[str, str]:
        return {"type": type(m).__name__}

    with TestClient(app) as client:
        assert set(client.get("/_test/repos").json()) == {
            "SqliteMeterRepository",
            "SqliteTransformerRepository",
            "SqliteReadingRepository",
            "SqliteSyncRepository",
        }
        assert client.get("/_test/meter-repo").json() == {"type": "SqliteMeterRepository"}
        app.dependency_overrides[get_meter_repository] = lambda: FakeMeters()
        assert client.get("/_test/meter-repo").json() == {"type": "FakeMeters"}


def test_connection_commits_on_success_and_rolls_back_on_error(
    settings: Settings,
) -> None:
    app: FastAPI = create_app(settings)
    meter = _a_meter()

    @app.post("/_test/ok")
    async def ok(m: Annotated[MeterRepository, Depends(get_meter_repository)]) -> dict[str, int]:
        await m.upsert_many([meter], datetime(2026, 1, 1, tzinfo=UTC))
        return {"n": 1}

    @app.post("/_test/boom")
    async def boom(m: Annotated[MeterRepository, Depends(get_meter_repository)]) -> None:
        await m.upsert_many([_a_meter("J2")], datetime(2026, 1, 1, tzinfo=UTC))
        raise RuntimeError("boom")

    @app.get("/_test/count")
    async def count(m: Annotated[MeterRepository, Depends(get_meter_repository)]) -> dict[str, int]:
        return {"n": await m.count()}

    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.post("/_test/boom").status_code == 500
        assert client.get("/_test/count").json() == {"n": 0}
        assert client.post("/_test/ok").status_code == 200
        assert client.get("/_test/count").json() == {"n": 1}


def _a_meter(meter_id: str = "J1") -> Meter:
    from app.domain.models import InstallStatus, PhaseType

    return Meter(
        meter_id,
        "S",
        "Acme",
        PhaseType.SINGLE,
        InstallStatus.INSTALLED,
        None,
        None,
        None,
        None,
        None,
    )


def test_commit_happens_before_the_response_is_sent(settings: Settings) -> None:
    """A failing commit must surface as a 500, not a 200 followed by a silent failure."""
    from sqlalchemy import event

    app: FastAPI = create_app(settings)

    @app.post("/_test/write")
    async def write(m: Annotated[MeterRepository, Depends(get_meter_repository)]) -> dict[str, int]:
        await m.upsert_many([_a_meter()], datetime(2026, 1, 1, tzinfo=UTC))
        return {"n": 1}

    def fail_commit(_conn: Any) -> None:
        raise RuntimeError("commit failed")

    with TestClient(app, raise_server_exceptions=False) as client:
        # armed after startup, whose own transaction must still commit
        event.listen(app.state.db_engine.sync_engine, "commit", fail_commit)
        assert client.post("/_test/write").status_code == 500
