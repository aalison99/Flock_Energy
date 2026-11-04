"""Shared fixtures: explicit settings (never read from .env), an app and a client."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

pytest_plugins = ["tests.support.db"]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Test settings; the database is a migrated-on-startup temp file, never ./urja.db."""
    return Settings(
        db_url=f"sqlite:///{tmp_path / 'app.db'}",
        environment="test",
        sync_on_startup=False,  # no background portal traffic unless a test asks for it
        portal_url="https://portal.example.test",  # type: ignore[arg-type]
        portal_email="tester@example.test",
        portal_password="s3cret-value",  # type: ignore[arg-type]
        _env_file=None,
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
