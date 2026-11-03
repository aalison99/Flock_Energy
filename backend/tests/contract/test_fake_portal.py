"""Runs the PortalClient contract against the fixture-backed fake."""

from pathlib import Path

import pytest

from app.portal.fake import FakePortalClient
from app.portal.interfaces import PortalClient
from tests.contract.portal_contract import PortalClientContract

FIXTURES = Path(__file__).parents[1] / "fixtures" / "portal"


class TestFakePortal(PortalClientContract):
    @pytest.fixture
    def portal(self) -> PortalClient:
        return FakePortalClient(FIXTURES)
