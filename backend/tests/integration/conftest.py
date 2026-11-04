"""Fixtures for API tests: the real app with fake portal collaborators swapped in."""

from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.deps import get_breaker_state, get_freshness, get_portal
from app.main import create_app
from app.portal.fake import FakePortalClient
from tests.support.fakes import FakeBreaker, FakeFreshness
from tests.support.portal_emulator import FIXTURES


@dataclass
class Api:
    app: FastAPI
    client: TestClient
    portal: FakePortalClient
    freshness: FakeFreshness
    breaker: FakeBreaker


@pytest.fixture
def api(settings: Settings) -> Iterator[Api]:
    app = create_app(settings)
    portal = FakePortalClient(FIXTURES)
    freshness = FakeFreshness()
    breaker = FakeBreaker()
    app.dependency_overrides[get_portal] = lambda: portal
    app.dependency_overrides[get_freshness] = lambda: freshness
    app.dependency_overrides[get_breaker_state] = lambda: breaker
    with TestClient(app, raise_server_exceptions=False) as client:
        yield Api(app, client, portal, freshness, breaker)
