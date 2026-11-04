from app.portal.interfaces import BreakerState
from tests.integration.conftest import Api


def test_ready_when_closed(api: Api) -> None:
    r = api.client.get("/api/v1/health/ready")
    assert r.status_code == 200
    assert r.json() == {
        "status": "ready",
        "portal": {"breaker": "closed"},
        "index": {"ready": False, "meter_count": 0, "last_sync_at": None},
    }
    assert r.headers["X-Request-ID"]


def test_ready_when_half_open(api: Api) -> None:
    api.breaker.state = BreakerState.HALF_OPEN
    r = api.client.get("/api/v1/health/ready")
    assert r.status_code == 200
    assert r.json()["portal"]["breaker"] == "half_open"


def test_not_ready_when_open_is_503_with_same_shape(api: Api) -> None:
    api.breaker.state = BreakerState.OPEN
    r = api.client.get("/api/v1/health/ready")
    assert r.status_code == 503
    assert r.json()["status"] == "not_ready"
    assert r.json()["portal"] == {"breaker": "open"}
    assert r.json()["index"]["ready"] is False
    assert r.headers["X-Request-ID"]


def test_readiness_makes_no_portal_calls(api: Api) -> None:
    api.client.get("/api/v1/health/ready")
    assert api.portal.calls == []


def test_liveness_still_ok(api: Api) -> None:
    assert api.client.get("/api/v1/health").json()["status"] == "ok"
