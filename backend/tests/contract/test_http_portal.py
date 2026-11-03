"""Runs the PortalClient contract against HttpPortalClient over the portal emulator."""

from collections.abc import AsyncIterator

import pytest

from app.portal.interfaces import PortalClient
from tests.contract.portal_contract import PortalClientContract
from tests.support.http_helpers import build_client
from tests.support.portal_emulator import PortalEmulator


class TestHttpPortal(PortalClientContract):
    @pytest.fixture
    async def portal(self) -> AsyncIterator[PortalClient]:
        client = build_client(PortalEmulator())
        yield client
        await client.aclose()
