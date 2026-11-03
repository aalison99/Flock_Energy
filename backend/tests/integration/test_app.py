from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.config import Settings
from app.core.deps import get_settings
from app.main import create_app


def test_health(client: TestClient) -> None:
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "version": "0.1.0"}


def test_unknown_route_404_envelope(client: TestClient) -> None:
    r = client.get("/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"
    assert r.json()["error"]["details"] == {}


def test_405_envelope(client: TestClient) -> None:
    r = client.post("/api/v1/health")
    assert r.status_code == 405
    assert r.json()["error"]["code"] == "method_not_allowed"


def test_unhandled_error_500_with_request_id(app: FastAPI, client: TestClient) -> None:
    @app.get("/explode")
    def explode() -> None:
        raise RuntimeError("secret internals")

    r = client.get("/explode")
    assert r.status_code == 500
    err = r.json()["error"]
    assert err["code"] == "internal_error"
    assert err["message"] == "Internal server error"
    assert "secret internals" not in r.text
    assert err["details"]["request_id"] == r.headers["X-Request-ID"]


def test_instances_have_independent_overrides(settings: Settings) -> None:
    a, b = create_app(settings), create_app(settings)
    for app in (a, b):

        @app.get("/env")
        def env(s: Annotated[Settings, Depends(get_settings)]) -> str:
            return s.environment

    a.dependency_overrides[get_settings] = lambda: settings.model_copy(
        update={"environment": "prod"}
    )
    assert b.dependency_overrides == {}
    assert TestClient(a).get("/env").json() == "prod"
    assert TestClient(b).get("/env").json() == "test"
    assert a.state.settings is settings and b.state.settings is settings


def test_clock_is_wired_by_deps(app: FastAPI) -> None:
    from app.core.clock import SystemClock

    assert isinstance(app.state.clock, SystemClock)


def test_docs_html(client: TestClient) -> None:
    r = client.get("/docs")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_main_is_small() -> None:
    main = Path(__file__).resolve().parents[2] / "app" / "main.py"
    assert len(main.read_text().splitlines()) < 100


def test_exception_in_dependency_is_500_envelope(app: FastAPI, client: TestClient) -> None:
    def bad_dep() -> None:
        raise RuntimeError("dep failed")

    @app.get("/dep")
    def dep(_: Annotated[None, Depends(bad_dep)]) -> None: ...

    r = client.get("/dep", headers={"X-Request-ID": "mine-1"})
    assert r.status_code == 500
    assert r.headers["X-Request-ID"] == "mine-1"
    assert r.json()["error"]["details"]["request_id"] == "mine-1"


def test_validation_error_through_full_app(app: FastAPI, client: TestClient) -> None:
    @app.get("/n")
    def n(count: int) -> int:
        return count

    r = client.get("/n?count=abc")
    assert r.status_code == 422
    err = r.json()["error"]
    assert (err["code"], err["message"]) == ("validation_error", "Request validation failed")
    assert set(err["details"]["errors"][0]) == {"loc", "msg", "type"}


def test_malformed_json_body_is_422_envelope(app: FastAPI, client: TestClient) -> None:
    class Body(BaseModel):
        a: int

    @app.post("/b")
    def b(body: Body) -> int:
        return body.a

    r = client.post("/b", content="{not json", headers={"Content-Type": "application/json"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


def _raising(app: FastAPI) -> None:
    @app.get("/explode")
    def explode() -> None:
        raise RuntimeError("x")


def test_500_has_cors_for_allowed_origin(app: FastAPI, client: TestClient) -> None:
    _raising(app)
    r = client.get("/explode", headers={"Origin": "http://localhost:5173"})
    assert r.status_code == 500
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_500_has_no_cors_for_other_origin(app: FastAPI, client: TestClient) -> None:
    _raising(app)
    r = client.get("/explode", headers={"Origin": "http://evil.example"})
    assert r.status_code == 500
    assert "access-control-allow-origin" not in r.headers


def test_openapi_documents_error_envelope(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    schemas = spec["components"]["schemas"]
    assert "ErrorResponse" in schemas
    assert "HTTPValidationError" not in schemas
    responses = spec["paths"]["/api/v1/health"]["get"]["responses"]
    for status in ("404", "422", "500"):
        ref = responses[status]["content"]["application/json"]["schema"]["$ref"]
        assert ref.endswith("/ErrorResponse")
