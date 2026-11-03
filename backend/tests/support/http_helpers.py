"""Builders shared by the HTTP portal tests: a fixed clock and an emulator-backed client."""

from collections.abc import Callable
from datetime import UTC, datetime

import httpx

from app.portal.http_client import HttpPortalClient
from app.portal.parsers.registry import default_registry
from app.portal.secret import Secret
from app.portal.session import PortalCredentials, PortalSession
from app.portal.signer import HmacSha256Signer
from tests.support.portal_emulator import PortalEmulator

BASE_URL = "https://portal.example.test"
NOW = datetime(2026, 11, 4, 12, 0, 0, tzinfo=UTC)


class FixedClock:
    def __init__(self, now: datetime = NOW) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


def build_client(
    emulator: PortalEmulator,
    clock: FixedClock | None = None,
    handler: Callable[[httpx.Request], httpx.Response] | None = None,
) -> HttpPortalClient:
    """A client over the emulator; `handler` may wrap `emulator.handle` to tamper with traffic."""
    session = PortalSession(
        BASE_URL,
        PortalCredentials("tester@example.test", Secret(emulator.password)),
        timeout_s=5,
        transport=httpx.MockTransport(handler or emulator.handle),
    )
    return HttpPortalClient(session, default_registry(), HmacSha256Signer(), clock or FixedClock())
