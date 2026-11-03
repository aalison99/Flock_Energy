import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import STATUS_BY_ERROR, status_for
from app.domain import exceptions as exc


def _raiser(error: exc.DomainError) -> FastAPI:
    from app.core.errors import register_error_handlers

    app = FastAPI()
    register_error_handlers(app)

    @app.get("/boom")
    def boom() -> None:
        raise error

    return app


@pytest.mark.parametrize(
    ("cls", "code", "status"),
    [
        (exc.ValidationError, "validation_error", 422),
        (exc.NotFoundError, "not_found", 404),
        (exc.ConflictError, "conflict", 409),
        (exc.IndexNotReadyError, "index_not_ready", 409),
        (exc.UpstreamAuthError, "upstream_auth_failed", 502),
        (exc.UpstreamProtocolError, "upstream_protocol_error", 502),
        (exc.UpstreamUnavailableError, "upstream_unavailable", 503),
    ],
)
def test_domain_error_maps_to_envelope(cls: type[exc.DomainError], code: str, status: int) -> None:
    client = TestClient(_raiser(cls("nope", {"k": 1})))
    r = client.get("/boom")
    assert r.status_code == status
    assert r.json() == {"error": {"code": code, "message": "nope", "details": {"k": 1}}}
    assert STATUS_BY_ERROR[cls] == status


def test_subclass_walks_mro() -> None:
    class MissingMeter(exc.NotFoundError):
        pass

    assert status_for(MissingMeter("x")) == 404
    r = TestClient(_raiser(MissingMeter("x"))).get("/boom")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_unknown_domain_error_is_500() -> None:
    class Weird(exc.DomainError):
        code = "weird"

    r = TestClient(_raiser(Weird("x"))).get("/boom")
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "weird"


def test_retry_after_header() -> None:
    r = TestClient(_raiser(exc.UpstreamUnavailableError("down", retry_after_s=7))).get("/boom")
    assert r.status_code == 503
    assert r.headers["Retry-After"] == "7"


def test_no_retry_after_when_unset() -> None:
    r = TestClient(_raiser(exc.UpstreamUnavailableError("down"))).get("/boom")
    assert "Retry-After" not in r.headers


def test_defaults() -> None:
    e = exc.NotFoundError("m")
    assert e.details == {}
    assert e.message == "m"


def test_unmapped_domain_error_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    class Weird(exc.DomainError):
        code = "weird"

    with caplog.at_level("ERROR", logger="urja.errors"):
        TestClient(_raiser(Weird("x"))).get("/boom")
    assert any(r.levelname == "ERROR" and r.exc_info for r in caplog.records)


def test_client_errors_are_not_logged_as_errors(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("ERROR", logger="urja.errors"):
        TestClient(_raiser(exc.NotFoundError("x"))).get("/boom")
    assert not caplog.records


def test_500_request_id_falls_back_when_middleware_absent() -> None:
    app = FastAPI()
    from app.core.errors import register_error_handlers

    register_error_handlers(app)

    @app.get("/x")
    def x() -> None:
        raise RuntimeError("boom")

    r = TestClient(app, raise_server_exceptions=False).get("/x")
    rid = r.headers["X-Request-ID"]
    assert rid
    assert r.json()["error"]["details"]["request_id"] == rid
