"""Runs the PortalClient contract against the real portal (opt-in: `make test-live`)."""

import os
from collections.abc import AsyncIterator

import pytest

from app.core.clock import SystemClock
from app.core.config import ENV_FILE, load_settings
from app.portal.http_client import HttpPortalClient
from app.portal.interfaces import PortalClient
from app.portal.parsers.registry import default_registry
from app.portal.secret import Secret
from app.portal.session import PortalCredentials, PortalSession
from app.portal.signer import HmacSha256Signer
from tests.contract.portal_contract import PortalClientContract

pytestmark = pytest.mark.live

_PASSWORD_VAR = "URJA_PORTAL_PASSWORD"


def _has_credentials() -> bool:
    if os.environ.get(_PASSWORD_VAR):
        return True
    try:
        lines = ENV_FILE.read_text().splitlines()
    except OSError:
        return False
    return any(line.startswith(f"{_PASSWORD_VAR}=") for line in lines)


@pytest.mark.skipif(not _has_credentials(), reason=f"{_PASSWORD_VAR} not set (env or .env)")
class TestLivePortal(PortalClientContract):
    @pytest.fixture
    async def portal(self) -> AsyncIterator[PortalClient]:
        settings = load_settings()
        credentials = PortalCredentials(
            settings.portal_email, Secret(settings.portal_password.get_secret_value())
        )
        session = PortalSession(
            str(settings.portal_url), credentials, timeout_s=settings.http_timeout_s
        )
        client = HttpPortalClient(session, default_registry(), HmacSha256Signer(), SystemClock())
        yield client
        await client.aclose()
