from datetime import UTC, datetime

from app.domain.exceptions import UpstreamUnavailableError
from tests.integration.conftest import Api

URL = "/api/v1/meters/J100000/readings"


def test_raw_shape_and_iso_offsets(api: Api) -> None:
    r = api.client.get(URL)
    assert r.status_code == 200
    body = r.json()
    assert body["buckets"] is None
    assert (body["resolution"], body["interval_minutes"], body["interval_kind"]) == (
        "raw",
        30,
        "half_hourly",
    )
    assert len(body["points"]) == 337
    assert body["points"][0]["interval_start"] is None
    assert body["points"][1] == {
        "at": "2026-06-24T00:00:00+05:30",
        "interval_start": "2026-06-23T23:30:00+05:30",
        "kwh_register": 48439.16,
        "kvah_register": 52314.29,
        "voltage_r": 229.0,
        "kwh": 0.42,
        "kvah": 0.45,
        "power_factor": 0.933,
        "flags": [],
    }
    assert body["summary"]["first_at"] == "2026-06-23T23:30:00+05:30"
    assert body["summary"]["total_kwh"] == 142.05
    assert body["meta"]["source"] == "portal"
    assert r.headers["X-Request-ID"]


def test_hourly_shape(api: Api) -> None:
    body = api.client.get(URL, params={"resolution": "hourly"}).json()
    assert body["points"] is None
    first = body["buckets"][0]
    assert first["start"] == "2026-06-23T23:00:00+05:30"
    assert first["end"] == "2026-06-24T00:00:00+05:30"
    assert first["readings"] == 1
    assert body["buckets"][1]["readings"] == 2


def test_daily_shape(api: Api) -> None:
    body = api.client.get(URL, params={"resolution": "daily"}).json()
    assert [b["start"][:10] for b in body["buckets"]] == [
        f"2026-06-{d}" for d in (23, 24, 25, 26, 27, 28, 29, 30)
    ]
    assert body["buckets"][2]["start"] == "2026-06-25T00:00:00+05:30"
    assert body["buckets"][2]["readings"] == 48


def test_date_range(api: Api) -> None:
    body = api.client.get(URL, params={"start": "2026-06-29", "end": "2026-06-30"}).json()
    assert len(body["points"]) == 96
    assert body["points"][0]["at"] == "2026-06-29T00:00:00+05:30"


def test_out_of_window_is_empty_200(api: Api) -> None:
    r = api.client.get(URL, params={"start": "2030-01-01"})
    assert r.status_code == 200
    body = r.json()
    assert body["points"] == []
    assert (body["interval_minutes"], body["interval_kind"]) == (None, "unknown")
    assert body["summary"]["readings"] == 0 and body["summary"]["first_at"] is None


def test_start_after_end_is_422_envelope(api: Api) -> None:
    r = api.client.get(URL, params={"start": "2026-06-30", "end": "2026-06-29"})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "validation_error"
    assert err["details"] == {"start": "2026-06-30", "end": "2026-06-29"}
    assert api.portal.calls == []


def test_bad_resolution_is_422(api: Api) -> None:
    r = api.client.get(URL, params={"resolution": "weekly"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"
    assert r.headers["X-Request-ID"]


def test_bad_date_is_422(api: Api) -> None:
    assert api.client.get(URL, params={"start": "24/06/2026"}).status_code == 422


def test_short_id_is_422(api: Api) -> None:
    assert api.client.get("/api/v1/meters/J12/readings").status_code == 422
    assert api.portal.calls == []


def test_unknown_meter_is_404(api: Api) -> None:
    r = api.client.get("/api/v1/meters/J999999/readings")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_daily_meter_hourly_is_422_with_details(api: Api) -> None:
    r = api.client.get("/api/v1/meters/J100402/readings", params={"resolution": "hourly"})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["details"] == {"resolution": "hourly", "interval_minutes": 1440}


def test_daily_meter_daily_ok(api: Api) -> None:
    body = api.client.get("/api/v1/meters/J100402/readings", params={"resolution": "daily"}).json()
    assert body["interval_kind"] == "daily"
    assert len(body["buckets"]) == 7


def test_upstream_unavailable_503_with_retry_after(api: Api) -> None:
    api.portal.fail("get_readings", UpstreamUnavailableError("down", retry_after_s=7))
    r = api.client.get(URL)
    assert r.status_code == 503
    assert r.headers["Retry-After"] == "7"
    assert r.headers["X-Request-ID"]


def test_meta_from_freshness(api: Api) -> None:
    at = datetime(2026, 11, 4, 9, tzinfo=UTC)
    api.freshness.set(
        "get_readings", "J100000", None, None, fetched_at=at, expires_at=at, stale=True
    )
    meta = api.client.get(URL).json()["meta"]
    assert meta == {"source": "portal", "fetched_at": "2026-11-04T09:00:00Z", "stale": True}
