"""PortalSession: lazy login, expiry replay, login-storm control, error mapping, secrecy."""

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable

import httpx
import pytest

from app.domain.exceptions import (
    NotFoundError,
    UpstreamAuthError,
    UpstreamProtocolError,
    UpstreamUnavailableError,
)
from app.portal.parsers.registry import PayloadKind, default_registry
from app.portal.secret import Secret
from app.portal.session import PortalCredentials, PortalSession
from tests.support.portal_emulator import PortalEmulator

pytestmark = pytest.mark.anyio

BASE = "https://portal.example.test"
PARSERS = default_registry()


def geo(response: httpx.Response) -> object:
    return PARSERS.parse(PayloadKind.GEO, response.content)


def detail(response: httpx.Response) -> object:
    return PARSERS.parse(PayloadKind.METER_DETAIL, response.content)


def status_of(response: httpx.Response) -> int:
    return response.status_code


@pytest.fixture
def emulator() -> PortalEmulator:
    return PortalEmulator()


def make_session(
    handler: Callable[[httpx.Request], httpx.Response], password: str = "emulator-password"
) -> PortalSession:
    return PortalSession(
        BASE,
        PortalCredentials("tester@example.test", Secret(password)),
        timeout_s=5,
        transport=httpx.MockTransport(handler),
    )


@pytest.fixture
async def session(emulator: PortalEmulator) -> AsyncIterator[PortalSession]:
    s = make_session(emulator.handle)
    yield s
    await s.aclose()


async def test_lazy_login(emulator: PortalEmulator, session: PortalSession) -> None:
    assert emulator.requests == []
    await session.request("GET", "/portal/meters/J100000/geo", parse=geo)
    assert emulator.requests[0] == ("POST", "/login")
    assert emulator.logins == 1
    await session.request("GET", "/portal/meters/J100000/geo", parse=geo)
    assert emulator.logins == 1


async def test_login_headers_and_form(emulator: PortalEmulator, session: PortalSession) -> None:
    await session.request("GET", "/portal/meters/J100000/geo", parse=geo)
    login = emulator.request_log[0]
    assert login.headers["origin"] == BASE
    assert login.headers["x-sveltekit-action"] == "true"
    assert login.headers["user-agent"] == "urja-meter-api/0.1"
    assert login.headers["accept"] == "application/json"
    assert dict(httpx.QueryParams(login.content.decode())) == {
        "email": "tester@example.test",
        "password": "emulator-password",
    }


async def test_bad_password(emulator: PortalEmulator) -> None:
    s = make_session(emulator.handle, password="wrong")
    with pytest.raises(UpstreamAuthError, match="Invalid email or password"):
        await s.request("GET", "/portal/meters/J100000/geo", parse=geo)
    await s.aclose()


async def test_login_forbidden(emulator: PortalEmulator) -> None:
    def no_origin(request: httpx.Request) -> httpx.Response:
        request.headers.pop("origin", None)
        return emulator.handle(request)

    s = make_session(no_origin)
    with pytest.raises(UpstreamAuthError, match="login rejected: HTTP 403"):
        await s.request("GET", "/portal/meters/J100000/geo", parse=geo)
    await s.aclose()


@pytest.mark.parametrize(
    ("path", "parse"),
    [
        ("/portal/meters/J100000/geo", geo),  # 401 JSON body
        ("/meters/J100000/__data.json", detail),  # 200 route-data redirect
        ("/meters", status_of),  # 302 to /login
    ],
    ids=["portal-401", "route-data-redirect", "html-302"],
)
async def test_each_expiry_signal_relogs_in_once(
    emulator: PortalEmulator,
    session: PortalSession,
    path: str,
    parse: Callable[[httpx.Response], object],
) -> None:
    await session.request("GET", path, parse=parse)
    assert emulator.logins == 1
    emulator.expire_sessions()
    result = await session.request("GET", path, parse=parse)
    assert result is not None
    assert emulator.logins == 2
    assert emulator.requests.count(("GET", path)) == 3  # first, expired, replay


async def test_headers_factory_called_again_on_replay(
    emulator: PortalEmulator, session: PortalSession
) -> None:
    calls: list[int] = []

    async def factory() -> dict[str, str]:
        calls.append(1)
        return {"x-n": str(len(calls))}

    await session.request("GET", "/portal/meters/J100000/geo", parse=geo)
    emulator.expire_sessions()
    await session.request("GET", "/portal/meters/J100000/geo", headers_factory=factory, parse=geo)
    assert len(calls) == 2
    assert emulator.request_log[-1].headers["x-n"] == "2"


async def test_still_expired_after_relogin(emulator: PortalEmulator) -> None:
    def broken(request: httpx.Request) -> httpx.Response:
        response = emulator.handle(request)
        if request.url.path == "/login":
            emulator.expire_sessions()
        return response

    s = make_session(broken)
    with pytest.raises(UpstreamAuthError, match="session could not be re-established"):
        await s.request("GET", "/portal/meters/J100000/geo", parse=geo)
    assert emulator.logins == 2
    await s.aclose()


def gated(
    emulator: PortalEmulator, n: int, timeout: float = 2.0
) -> Callable[[httpx.Request], Awaitable[httpx.Response]]:
    """Async handler: holds the first n expired (401) answers until all n have been decided."""
    arrived = 0
    release = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal arrived
        if request.url.path == "/login":
            await asyncio.sleep(0.01)  # give racing logins a chance to overlap
            return emulator.handle(request)
        response = emulator.handle(request)  # decided now, under the cookie that was sent
        if response.status_code == 401 and arrived < n:
            arrived += 1
            if arrived == n:
                release.set()
            await asyncio.wait_for(release.wait(), timeout)  # a stuck barrier fails, not hangs
        return response

    return handler


async def test_concurrent_expiry_causes_one_relogin(emulator: PortalEmulator) -> None:
    session = make_session(gated(emulator, 10))  # type: ignore[arg-type]
    await session.request("GET", "/portal/meters/J100000/geo", parse=geo)
    emulator.expire_sessions()
    results = await asyncio.gather(
        *(session.request("GET", "/portal/meters/J100000/geo", parse=geo) for _ in range(10))
    )
    assert len(results) == 10
    assert emulator.logins == 2
    await session.aclose()


async def test_stuck_barrier_fails_instead_of_hanging(emulator: PortalEmulator) -> None:
    session = make_session(gated(emulator, 11, timeout=0.1))  # type: ignore[arg-type]
    await session.request("GET", "/portal/meters/J100000/geo", parse=geo)
    emulator.expire_sessions()
    with pytest.raises(TimeoutError):
        await asyncio.gather(
            *(session.request("GET", "/portal/meters/J100000/geo", parse=geo) for _ in range(10))
        )
    await session.aclose()


async def test_concurrent_first_requests_login_once(emulator: PortalEmulator) -> None:
    session = make_session(gated(emulator, 0))  # type: ignore[arg-type]
    await asyncio.gather(
        *(session.request("GET", "/portal/meters/J100000/geo", parse=geo) for _ in range(5))
    )
    assert emulator.logins == 1
    await session.aclose()


async def test_request_failing_after_a_relogin_replays_without_logging_in(
    emulator: PortalEmulator,
) -> None:
    """A was sent under generation 1 and fails after B re-logged in (generation 2)."""

    async def handler(request: httpx.Request) -> httpx.Response:
        response = emulator.handle(request)
        if request.headers.get("x-hold") and response.status_code == 401:
            async with asyncio.timeout(2.0):
                while emulator.logins < 2:  # hold A's 401 until B's re-login has completed
                    await asyncio.sleep(0)
        return response

    async def hold() -> dict[str, str]:
        return {"x-hold": "1"}

    session = make_session(handler)  # type: ignore[arg-type]
    await session.request("GET", "/portal/meters/J100000/geo", parse=geo)
    emulator.expire_sessions()
    a = asyncio.create_task(
        session.request("GET", "/portal/meters/J100000/geo", headers_factory=hold, parse=geo)
    )
    for _ in range(5):
        await asyncio.sleep(0)  # let A send and start waiting
    await session.request("GET", "/portal/meters/J100000/geo", parse=geo)  # B re-logs in
    assert emulator.logins == 2
    await a
    assert emulator.logins == 2
    await session.aclose()


@pytest.mark.parametrize(
    "exception",
    [httpx.ConnectTimeout("t"), httpx.ConnectError("c"), httpx.RemoteProtocolError("r")],
)
async def test_transport_errors(
    emulator: PortalEmulator, session: PortalSession, exception: Exception
) -> None:
    await session.request("GET", "/portal/meters/J100000/geo", parse=geo)
    emulator.fail_next(1, exception=exception)
    with pytest.raises(
        UpstreamUnavailableError, match=f"portal unreachable: {type(exception).__name__}"
    ):
        await session.request("GET", "/portal/meters/J100000/geo", parse=geo)


async def test_transport_error_during_login(
    emulator: PortalEmulator, session: PortalSession
) -> None:
    emulator.fail_next(1, exception=httpx.ConnectError("c"))
    with pytest.raises(UpstreamUnavailableError, match="portal unreachable: ConnectError"):
        await session.request("GET", "/portal/meters/J100000/geo", parse=geo)


async def test_503(emulator: PortalEmulator, session: PortalSession) -> None:
    await session.request("GET", "/portal/meters/J100000/geo", parse=geo)
    emulator.fail_next(1, status=503)
    with pytest.raises(UpstreamUnavailableError, match="portal error: HTTP 503"):
        await session.request("GET", "/portal/meters/J100000/geo", parse=geo)


def fixed_status(emulator: PortalEmulator, response: httpx.Response) -> PortalSession:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/login":
            return emulator.handle(request)
        return response

    return make_session(handler)


async def test_429_retry_after(emulator: PortalEmulator) -> None:
    s = fixed_status(emulator, httpx.Response(429, headers={"Retry-After": "7"}))
    with pytest.raises(UpstreamUnavailableError) as info:
        await s.request("GET", "/portal/dts", parse=geo)
    assert info.value.retry_after_s == 7
    await s.aclose()


@pytest.mark.parametrize("value", ["soon", "-3", "1.5", "\u00b2", "\u0663", None])
async def test_429_unparseable_retry_after_is_ignored(
    emulator: PortalEmulator, value: str | None
) -> None:
    raw = [] if value is None else [(b"retry-after", value.encode())]
    s = fixed_status(emulator, httpx.Response(429, headers=raw))
    with pytest.raises(UpstreamUnavailableError) as info:
        await s.request("GET", "/portal/dts", parse=geo)
    assert info.value.retry_after_s is None
    await s.aclose()


async def test_400_is_protocol_error(emulator: PortalEmulator) -> None:
    s = fixed_status(emulator, httpx.Response(400, content=b"bad"))
    with pytest.raises(UpstreamProtocolError):
        await s.request("GET", "/portal/dts", parse=geo)
    await s.aclose()


async def test_404_body_reaches_parser(emulator: PortalEmulator, session: PortalSession) -> None:
    with pytest.raises(NotFoundError):
        await session.request("GET", "/portal/meters/NOPE/geo", parse=geo)


async def test_no_secrets_in_logs_or_reprs(
    emulator: PortalEmulator, session: PortalSession, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    await session.request("GET", "/portal/meters/J100000/geo", parse=geo)
    emulator.expire_sessions()
    await session.request("GET", "/portal/meters/J100000/geo", parse=geo)
    messages = [r.getMessage() for r in caplog.records if r.name.startswith("app.")]
    assert "portal login ok" in messages
    assert "portal re-login (generation 2)" in messages
    blob = caplog.text + repr(session) + str(session)
    for secret in ("emulator-password", "token-1", "token-2"):
        assert secret not in blob
    creds = PortalCredentials("a@b.c", Secret("pw-123"))
    assert "pw-123" not in repr(creds)


async def test_aclose_signs_out_and_is_idempotent(emulator: PortalEmulator) -> None:
    s = make_session(emulator.handle)
    await s.request("GET", "/portal/meters/J100000/geo", parse=geo)
    await s.aclose()
    assert emulator.requests[-1] == ("POST", "/api/auth/sign-out")
    assert emulator.request_log[-1].headers["origin"] == BASE
    n = len(emulator.requests)
    await s.aclose()
    assert len(emulator.requests) == n


async def test_aclose_without_login_makes_no_request(emulator: PortalEmulator) -> None:
    s = make_session(emulator.handle)
    await s.aclose()
    assert emulator.requests == []


async def test_aclose_swallows_signout_errors(emulator: PortalEmulator) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/auth/sign-out":
            raise httpx.ConnectError("down")
        return emulator.handle(request)

    s = make_session(handler)
    await s.request("GET", "/portal/meters/J100000/geo", parse=geo)
    await s.aclose()
    await s.aclose()


@pytest.mark.parametrize("status", [429, 500, 503])
async def test_login_server_trouble_is_unavailable(status: int) -> None:
    s = make_session(lambda request: httpx.Response(status, headers={"Retry-After": "4"}))
    with pytest.raises(UpstreamUnavailableError) as info:
        await s.request("GET", "/portal/dts", parse=geo)
    assert info.value.retry_after_s == (4 if status == 429 else None)
    await s.aclose()


async def test_decoding_error_is_protocol_error(
    emulator: PortalEmulator, session: PortalSession
) -> None:
    await session.request("GET", "/portal/meters/J100000/geo", parse=geo)
    emulator.fail_next(1, exception=httpx.DecodingError("bad gzip"))
    with pytest.raises(UpstreamProtocolError, match="DecodingError"):
        await session.request("GET", "/portal/meters/J100000/geo", parse=geo)


async def test_request_after_aclose_is_unavailable(emulator: PortalEmulator) -> None:
    s = make_session(emulator.handle)
    await s.aclose()
    with pytest.raises(UpstreamUnavailableError, match="closed"):
        await s.request("GET", "/portal/dts", parse=geo)


async def test_aclose_closes_client_even_if_cancelled_during_signout(
    emulator: PortalEmulator,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/auth/sign-out":
            raise asyncio.CancelledError
        return emulator.handle(request)

    s = make_session(handler)  # type: ignore[arg-type]
    await s.request("GET", "/portal/meters/J100000/geo", parse=geo)
    with pytest.raises(asyncio.CancelledError):
        await s.aclose()
    assert s._client.is_closed


@pytest.mark.parametrize("url", ["http://portal.example.test", "portal.example.test", ""])
def test_non_https_base_url_rejected(url: str) -> None:
    with pytest.raises(ValueError, match="https"):
        PortalSession(url, PortalCredentials("a@b.c", Secret("pw")), timeout_s=1)


async def test_emulator_requires_matching_origin() -> None:
    emulator = PortalEmulator(origin="https://elsewhere.example.test")
    s = make_session(emulator.handle)
    with pytest.raises(UpstreamAuthError, match="login rejected: HTTP 403"):
        await s.request("GET", "/portal/meters/J100000/geo", parse=geo)
    await s.aclose()
