from datetime import UTC, datetime

import pytest

from app.domain.exceptions import (
    UpstreamAuthError,
    UpstreamProtocolError,
    UpstreamUnavailableError,
)
from tests.integration.conftest import Api

NOW = datetime(2026, 11, 4, 12, tzinfo=UTC)


def test_list_envelope_and_item_shape(api: Api) -> None:
    r = api.client.get("/api/v1/meters")
    assert r.status_code == 200
    body = r.json()
    assert (body["page"], body["page_size"], body["total"]) == (1, 50, 403)
    assert (body["total_pages"], body["has_next"]) == (9, True)
    assert len(body["items"]) == 50
    assert body["items"][0] == {
        "meter_id": "J100000",
        "serial_no": "SE33962",
        "make": "HPL",
        "phase_type": "single",
        "install_status": "decommissioned",
        "dt_code": "DT-001",
    }
    assert r.headers["X-Request-ID"]


def test_last_page(api: Api) -> None:
    body = api.client.get("/api/v1/meters?page=9&page_size=50").json()
    assert len(body["items"]) == 3
    assert body["has_next"] is False


def test_page_past_the_end(api: Api) -> None:
    body = api.client.get("/api/v1/meters?page=50").json()
    assert body["items"] == []
    assert body["total"] == 403


def test_q_search(api: Api) -> None:
    body = api.client.get("/api/v1/meters?q=se33962").json()
    assert body["total"] == 1
    assert body["items"][0]["meter_id"] == "J100000"
    assert body["total_pages"] == 1
    assert body["has_next"] is False


def test_q_too_long_is_422(api: Api) -> None:
    assert api.client.get("/api/v1/meters?q=" + "x" * 65).status_code == 422


def test_page_size_201_is_422_envelope(api: Api) -> None:
    r = api.client.get("/api/v1/meters?page_size=201")
    assert r.status_code == 422
    body = r.json()
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["details"]["errors"][0]["loc"] == ["query", "page_size"]
    assert r.headers["X-Request-ID"]


def test_detail_exact_body(api: Api) -> None:
    api.freshness.set("get_meter", "J100000", fetched_at=NOW, expires_at=NOW, stale=False)
    r = api.client.get("/api/v1/meters/J100000")
    assert r.status_code == 200
    assert r.json() == {
        "meter_id": "J100000",
        "serial_no": "SE33962",
        "make": "HPL",
        "phase_type": "single",
        "install_status": "decommissioned",
        "install_type": "whole_current",
        "build": "legacy",
        "dt_code": "DT-001",
        "hierarchy": [
            {"level": "zone", "code": "Z-01", "name": "Jaipur Zone 1"},
            {"level": "circle", "code": "C-01", "name": "Circle 1"},
            {"level": "division", "code": "D-01", "name": "Division 1"},
            {"level": "subdivision", "code": "SD-01", "name": "Subdivision 1"},
            {"level": "substation", "code": "SS-01", "name": "Substation 1"},
            {"level": "feeder", "code": "F-001", "name": "Feeder 1"},
            {"level": "dt", "code": "DT-001", "name": "Malviya Nagar DT 1"},
        ],
        "geo": {"lat": 26.938961002479868, "lng": 75.83095696146852},
        "meta": {"source": "portal", "fetched_at": "2026-11-04T12:00:00Z", "stale": False},
    }
    assert r.headers["X-Request-ID"]


def test_detail_stale_flag(api: Api) -> None:
    api.freshness.set("get_geo", "J100000", fetched_at=NOW, expires_at=NOW, stale=True)
    assert api.client.get("/api/v1/meters/J100000").json()["meta"]["stale"] is True


def test_short_id_is_422(api: Api) -> None:
    r = api.client.get("/api/v1/meters/J12")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"
    assert api.portal.calls == []


def test_unknown_meter_is_404(api: Api) -> None:
    r = api.client.get("/api/v1/meters/J999999")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"
    assert r.headers["X-Request-ID"]


def test_upstream_unavailable_503_with_retry_after(api: Api) -> None:
    api.portal.fail("list_meters", UpstreamUnavailableError("down", retry_after_s=12))
    r = api.client.get("/api/v1/meters")
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "upstream_unavailable"
    assert r.headers["Retry-After"] == "12"
    assert r.headers["X-Request-ID"]


def test_upstream_unavailable_without_retry_after(api: Api) -> None:
    api.portal.fail("get_meter", UpstreamUnavailableError("down"))
    r = api.client.get("/api/v1/meters/J100000")
    assert r.status_code == 503
    assert "Retry-After" not in r.headers


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (UpstreamProtocolError("bad payload"), "upstream_protocol_error"),
        (UpstreamAuthError("login failed"), "upstream_auth_failed"),
    ],
)
def test_upstream_protocol_or_auth_failure_is_502(api: Api, error: Exception, code: str) -> None:
    api.portal.fail("get_meter", error)
    r = api.client.get("/api/v1/meters/J100000")
    assert r.status_code == 502
    assert r.json()["error"]["code"] == code
    assert r.headers["X-Request-ID"]
    api.portal.fail("list_meters", error)
    assert api.client.get("/api/v1/meters").status_code == 502
