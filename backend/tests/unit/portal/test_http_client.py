"""HttpPortalClient: request mapping, signing, id encoding, error containment."""

import contextlib
import hashlib
import hmac
from collections.abc import AsyncIterator
from datetime import date
from urllib.parse import parse_qs

import httpx
import pytest

from app.domain.exceptions import (
    NotFoundError,
    UpstreamAuthError,
    UpstreamProtocolError,
    UpstreamUnavailableError,
    ValidationError,
)
from app.portal.errors import SessionExpired, SignatureRejected
from app.portal.http_client import HttpPortalClient
from tests.support.http_helpers import NOW, build_client
from tests.support.portal_emulator import PortalEmulator

pytestmark = pytest.mark.anyio


@pytest.fixture
def emulator() -> PortalEmulator:
    return PortalEmulator()


@pytest.fixture
async def client(emulator: PortalEmulator) -> AsyncIterator[HttpPortalClient]:
    c = build_client(emulator)
    yield c
    await c.aclose()


def data_calls(emulator: PortalEmulator) -> list[tuple[str, str, dict[str, list[str]]]]:
    """(method, path, query) for everything except login/sign-out."""
    return [
        (m, p, parse_qs(q))
        for (m, p), q in zip(emulator.requests, emulator.queries, strict=True)
        if p not in ("/login", "/api/auth/sign-out")
    ]


async def test_list_meters_mapping(client: HttpPortalClient, emulator: PortalEmulator) -> None:
    await client.list_meters(2, "se3")
    await client.list_meters(1)
    assert data_calls(emulator) == [
        ("GET", "/portal/meters/search", {"q": ["se3"], "page": ["2"]}),
        ("GET", "/portal/meters/search", {"page": ["1"]}),  # empty q is dropped by parse_qs
    ]
    assert emulator.queries[-1] == "q=&page=1"


async def test_get_meter_mapping(client: HttpPortalClient, emulator: PortalEmulator) -> None:
    await client.get_meter("J100086")
    assert data_calls(emulator) == [("GET", "/meters/J100086/__data.json", {})]


async def test_get_geo_mapping(client: HttpPortalClient, emulator: PortalEmulator) -> None:
    await client.get_geo("J100000")
    assert data_calls(emulator) == [("GET", "/portal/meters/J100000/geo", {})]


async def test_readings_params_only_when_given(
    client: HttpPortalClient, emulator: PortalEmulator
) -> None:
    await client.get_readings("J100402")
    await client.get_readings("J100402", date(2026, 6, 24))
    await client.get_readings("J100402", None, date(2026, 6, 25))
    await client.get_readings("J100402", date(2026, 6, 24), date(2026, 6, 25))
    assert [q for _, _, q in data_calls(emulator)] == [
        {},
        {"from": ["2026-06-24"]},
        {"to": ["2026-06-25"]},
        {"from": ["2026-06-24"], "to": ["2026-06-25"]},
    ]
    assert {p for _, p, _ in data_calls(emulator)} == {"/portal/meters/J100402/energy"}


async def test_readings_start_after_end(client: HttpPortalClient, emulator: PortalEmulator) -> None:
    with pytest.raises(ValidationError):
        await client.get_readings("J100000", date(2026, 6, 30), date(2026, 6, 29))
    assert emulator.requests == []


async def test_transformers_mapping(client: HttpPortalClient, emulator: PortalEmulator) -> None:
    await client.list_transformers(2)
    assert data_calls(emulator) == [("GET", "/portal/dts", {"page": ["2"]})]


@pytest.mark.parametrize("bad_id", [".", "..", "../x", "a/b", "", "a b", "J1\n", "-x", "x" * 65])
async def test_bad_ids_rejected_before_any_request(
    client: HttpPortalClient, emulator: PortalEmulator, bad_id: str
) -> None:
    for call in (client.get_meter, client.get_geo, client.get_readings):
        with pytest.raises(ValidationError):
            await call(bad_id)
    assert emulator.requests == []


async def test_valid_id_is_accepted(client: HttpPortalClient, emulator: PortalEmulator) -> None:
    with pytest.raises(NotFoundError):
        await client.get_geo("J999999")
    assert data_calls(emulator)[0][1] == "/portal/meters/J999999/geo"


async def test_signature_rejected_on_unsigned_endpoint_is_protocol_error(
    emulator: PortalEmulator,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/login":
            return emulator.handle(request)
        return httpx.Response(401, json={"error": "signature_invalid", "message": "x"})

    client = build_client(emulator, handler=handler)
    with pytest.raises(UpstreamProtocolError, match="GEO: unexpected signature rejection"):
        await client.get_geo("J100000")
    await client.aclose()


async def test_export_signs_with_clock(client: HttpPortalClient, emulator: PortalEmulator) -> None:
    meters = await client.bulk_export()
    assert len(meters) == 403
    assert [p for _, p, _ in data_calls(emulator)] == ["/portal/keys", "/portal/export"]
    request = emulator.request_log[-1]
    ts = int(NOW.timestamp())
    message = f"GET\n/portal/export\npage=1\n{ts}"
    expected = hmac.new(b"test-signing-secret", message.encode(), hashlib.sha256).hexdigest()
    assert request.headers["x-timestamp"] == str(ts)
    assert request.headers["x-signature"] == expected
    assert request.url.query == b"page=1"


def keys_calls(emulator: PortalEmulator) -> int:
    return emulator.requests.count(("GET", "/portal/keys"))


async def test_rotated_secret_refetches_once(emulator: PortalEmulator) -> None:
    # The secret rotates right after the first keys fetch, so the first export is rejected.
    rotated = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal rotated
        response = emulator.handle(request)
        if request.url.path == "/portal/keys" and not rotated:
            rotated = True
            emulator.rotate_secret("rotated-secret")
        return response

    client = build_client(emulator, handler=handler)
    assert len(await client.bulk_export()) == 403
    assert keys_calls(emulator) == 2
    assert emulator.requests.count(("GET", "/portal/export")) == 2
    await client.aclose()


async def test_still_rejected_is_auth_error(emulator: PortalEmulator) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        response = emulator.handle(request)
        if request.url.path == "/portal/keys":
            emulator.rotate_secret(emulator.secret + "x")  # always stale by the time we sign
        return response

    client = build_client(emulator, handler=handler)
    with pytest.raises(UpstreamAuthError, match="export signature rejected"):
        await client.bulk_export()
    assert keys_calls(emulator) == 2
    await client.aclose()


async def test_export_warns_when_total_exceeds_records(
    emulator: PortalEmulator, caplog: pytest.LogCaptureFixture
) -> None:
    import json

    def handler(request: httpx.Request) -> httpx.Response:
        response = emulator.handle(request)
        if request.url.path == "/portal/export" and response.status_code == 200:
            body = json.loads(response.content)
            body["total"] = 500
            return httpx.Response(200, json=body)
        return response

    client = build_client(emulator, handler=handler)
    with caplog.at_level("WARNING"):
        meters = await client.bulk_export()
    assert len(meters) == 403
    assert any("500" in r.getMessage() and r.levelname == "WARNING" for r in caplog.records)
    assert emulator.requests.count(("GET", "/portal/export")) == 1  # no page loop
    await client.aclose()


async def test_export_logs_no_secret(
    client: HttpPortalClient, emulator: PortalEmulator, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("DEBUG")
    await client.bulk_export()
    assert "test-signing-secret" not in caplog.text


async def test_export_survives_expired_session(
    client: HttpPortalClient, emulator: PortalEmulator
) -> None:
    await client.get_geo("J100000")
    emulator.expire_sessions()
    assert len(await client.bulk_export()) == 403


async def test_session_expired_and_signature_rejected_never_escape(
    emulator: PortalEmulator,
) -> None:
    def always_unauthorized(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/login":
            return emulator.handle(request)
        return httpx.Response(
            401,
            json={"error": "unauthorized", "message": "A valid session is required."},
        )

    client = build_client(emulator, handler=always_unauthorized)
    for call in (
        lambda: client.get_geo("J100000"),
        lambda: client.list_meters(1),
        client.bulk_export,
        lambda: client.get_meter("J100000"),
    ):
        with pytest.raises(UpstreamAuthError) as info:
            await call()
        assert not isinstance(info.value, SessionExpired | SignatureRejected)
    await client.aclose()


async def test_only_domain_errors_escape(emulator: PortalEmulator) -> None:
    """Whatever the portal answers with, callers only ever see the four upstream errors."""
    allowed = (NotFoundError, UpstreamAuthError, UpstreamUnavailableError, UpstreamProtocolError)
    bodies = [
        b"not json",
        b"[]",
        b'{"error":"signature_invalid"}',
        b'{"error":"unauthorized"}',
        b'{"type":"redirect","location":"/login"}',
    ]
    for body in bodies:

        def handler(request: httpx.Request, body: bytes = body) -> httpx.Response:
            if request.url.path == "/login":
                return emulator.handle(request)
            return httpx.Response(200, content=body)

        client = build_client(emulator, handler=handler)
        for name in ("get_geo", "get_meter"):
            with contextlib.suppress(*allowed):
                await getattr(client, name)("x")
        with contextlib.suppress(*allowed):
            await client.bulk_export()
        await client.aclose()
