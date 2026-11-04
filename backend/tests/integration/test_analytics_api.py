"""Analytics endpoints through the real app, SQLite index and sync, with the portal faked.

Only J100000 (half-hourly, decommissioned) and J100402 (daily) have energy fixtures; every other
fixture meter syncs with no readings.
"""

import json
from decimal import Decimal
from itertools import pairwise
from typing import Any

import pytest

from tests.integration.conftest import Api
from tests.support.portal_emulator import FIXTURES

BASE = "/api/v1/analytics"
HH = "J100000"
DAILY = "J100402"


def _raw(name: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = json.loads((FIXTURES / "energy" / name).read_text())["data"]
    return rows


def _oracle_total(rows: list[dict[str, str]], field: str) -> Decimal:
    """Sum of positive register differences, from the raw JSON, in Decimal."""
    values = [Decimal(r[field]) for r in rows]
    return sum((b - a for a, b in pairwise(values) if b >= a), Decimal(0))


@pytest.fixture
def full_api(api: Api) -> Api:
    """The app after a real sync that included readings."""
    assert api.client.post("/api/v1/sync", json={"include_readings": True}).status_code == 202
    api.client.portal.call(api.tasks.run_all)  # type: ignore[union-attr]
    latest = api.client.get("/api/v1/sync/status").json()["latest"]
    assert latest["status"] == "succeeded"
    return api


def _get(api: Api, path: str, **params: Any) -> Any:
    return api.client.get(path, params=params)


# --- 409 / 422 / 404 --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        f"{BASE}/summary",
        f"{BASE}/consumption",
        f"{BASE}/top-consumers",
        f"{BASE}/anomalies",
        f"{BASE}/transformers/load",
        f"/api/v1/meters/{HH}/anomalies",
    ],
)
def test_empty_index_is_409(api: Api, path: str) -> None:
    r = api.client.get(path)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "index_not_ready"


@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("consumption", {"resolution": "raw"}),
        ("consumption", {"node": "not-a-node"}),
        ("top-consumers", {"limit": 0}),
        ("top-consumers", {"limit": 101}),
        ("anomalies", {"severity": "fatal"}),
        ("anomalies", {"page_size": 201}),
        ("anomalies", {"page": 0}),
        ("transformers/load", {"sort": "sideways"}),
        ("transformers/load", {"limit": 101}),
    ],
)
def test_bad_parameters_are_422(full_api: Api, path: str, params: dict[str, Any]) -> None:
    r = _get(full_api, f"{BASE}/{path}", **params)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


def test_unknown_rule_is_422_listing_valid_rules(full_api: Api) -> None:
    r = _get(full_api, f"{BASE}/anomalies", rule="nope")
    assert r.status_code == 422
    assert "inactive_but_consuming" in r.json()["error"]["details"]["valid"]


def test_unknown_node_is_404(full_api: Api) -> None:
    node = "Z-98/C-98"
    for path in ("consumption", "top-consumers", "anomalies"):
        r = _get(full_api, f"{BASE}/{path}", node=node)
        assert r.status_code == 404, path


def test_unknown_meter_is_404_and_bad_id_422(full_api: Api) -> None:
    assert full_api.client.get("/api/v1/meters/J999999/anomalies").status_code == 404
    assert full_api.client.get("/api/v1/meters/bogus/anomalies").status_code == 422


# --- summary ----------------------------------------------------------------------------------


def test_summary_matches_independent_totals(full_api: Api) -> None:
    body = _get(full_api, f"{BASE}/summary").json()
    expected = _oracle_total(_raw("halfhourly_J100000.json"), "kwh") + _oracle_total(
        _raw("daily_J100402.json"), "kwh"
    )
    assert body["total_kwh"] == pytest.approx(float(expected), abs=1e-6)
    assert body["total_meters"] == 403
    assert body["reporting_meters"] == 2
    assert body["silent_meters"] == 401
    assert sum(body["meters_by_status"].values()) == 403
    assert body["interval_kinds"] == {"half_hourly": 1, "daily": 1, "unknown": 401}
    assert body["anomalies_by_rule"]["inactive_but_consuming"] >= 1
    assert set(body["anomalies_by_rule"]) == {
        "inactive_but_consuming",
        "voltage_out_of_band",
        "flatline",
        "register_reset",
        "data_gap",
        "consumption_spike",
    }
    assert body["first_reading_at"].endswith("+05:30")
    assert body["last_reading_at"].endswith("+05:30")


# --- consumption ------------------------------------------------------------------------------


def test_consumption_daily_default(full_api: Api) -> None:
    body = _get(full_api, f"{BASE}/consumption").json()
    assert body["resolution"] == "daily" and body["node"] is None
    assert (body["meters_included"], body["meters_excluded_coarser"]) == (2, 0)
    assert body["items"]
    first = body["items"][0]
    assert set(first) == {"start", "end", "kwh", "kvah", "meters"}
    assert first["start"].endswith("+05:30")
    # buckets sum to the fleet total
    total = sum(b["kwh"] for b in body["items"])
    summary = _get(full_api, f"{BASE}/summary").json()["total_kwh"]
    assert total == pytest.approx(summary, abs=1e-3)


def test_consumption_hourly_excludes_the_daily_meter(full_api: Api) -> None:
    body = _get(full_api, f"{BASE}/consumption", resolution="hourly").json()
    assert (body["meters_included"], body["meters_excluded_coarser"]) == (1, 1)
    expected = _oracle_total(_raw("halfhourly_J100000.json"), "kwh")
    assert sum(b["kwh"] for b in body["items"]) == pytest.approx(float(expected), abs=1e-3)
    assert {b["meters"] for b in body["items"]} == {1}


def test_consumption_for_a_node(full_api: Api) -> None:
    detail = full_api.client.get(f"/api/v1/meters/{HH}").json()
    zone = detail["hierarchy"][0]["code"]
    body = _get(full_api, f"{BASE}/consumption", node=zone, resolution="hourly").json()
    assert body["node"] == zone
    assert body["meters_included"] == 1


# --- top consumers ----------------------------------------------------------------------------


def test_top_consumers(full_api: Api) -> None:
    body = _get(full_api, f"{BASE}/top-consumers").json()
    ids = [row["meter"]["meter_id"] for row in body["items"]]
    assert set(ids) == {HH, DAILY}
    totals = [row["total_kwh"] for row in body["items"]]
    assert totals == sorted(totals, reverse=True)
    assert set(body["items"][0]["meter"]) >= {"meter_id", "serial_no", "install_status", "dt_code"}
    assert len(_get(full_api, f"{BASE}/top-consumers", limit=1).json()["items"]) == 1


# --- anomalies --------------------------------------------------------------------------------


def test_anomalies_page_envelope_and_rules(full_api: Api) -> None:
    body = _get(full_api, f"{BASE}/anomalies").json()
    assert set(body) == {
        "items", "page", "page_size", "total", "total_pages", "has_next", "rules",
    }  # fmt: skip
    assert [r["id"] for r in body["rules"]][:2] == ["inactive_but_consuming", "voltage_out_of_band"]
    assert set(body["rules"][0]) == {"id", "severity", "description"}
    severities = [a["severity"] for a in body["items"]]
    order = {"error": 0, "warning": 1, "info": 2}
    assert severities == sorted(severities, key=order.__getitem__)


def test_j100000_is_inactive_but_consuming(full_api: Api) -> None:
    body = _get(full_api, f"{BASE}/anomalies", rule="inactive_but_consuming").json()
    [item] = [a for a in body["items"] if a["meter_id"] == HH]
    assert item["severity"] == "error" and item["at"] is None
    assert item["evidence"]["install_status"] == "decommissioned"
    assert item["evidence"]["total_kwh"] == pytest.approx(142.05, abs=1e-6)


def test_anomalies_filter_by_severity_and_paging(full_api: Api) -> None:
    errors = _get(full_api, f"{BASE}/anomalies", severity="error").json()
    assert {a["severity"] for a in errors["items"]} <= {"error"}
    page = _get(full_api, f"{BASE}/anomalies", page_size=1).json()
    assert len(page["items"]) <= 1 and page["page_size"] == 1


def test_meter_anomalies(full_api: Api) -> None:
    body = full_api.client.get(f"/api/v1/meters/{HH}/anomalies").json()
    assert body["meter_id"] == HH
    assert "inactive_but_consuming" in {a["rule"] for a in body["items"]}
    silent = full_api.client.get("/api/v1/meters/J100001/anomalies").json()
    assert silent == {"meter_id": "J100001", "items": []} or silent["meter_id"] == "J100001"


# --- transformer load -------------------------------------------------------------------------


def test_transformer_load_shape_and_oracle(full_api: Api) -> None:
    body = _get(full_api, f"{BASE}/transformers/load").json()
    assert "ignores" in body["estimate_note"]
    assert "data gap" in body["estimate_note"] and "dt_code" in body["estimate_note"]
    items = body["items"]
    assert items and len(items) <= 40
    assert set(items[0]) == {
        "code", "name", "capacity_kva", "meter_count", "half_hourly_meters", "peak_kva_est",
        "avg_kva_est", "skipped_gap_intervals", "peak_at", "utilisation_pct", "overloaded",
    }  # fmt: skip
    dt_code = full_api.client.get(f"/api/v1/meters/{HH}").json()["dt_code"]
    row = next(i for i in items if i["code"] == dt_code)
    rows = _raw("halfhourly_J100000.json")
    kvah = [Decimal(r["kvah"]) for r in rows]
    peak = max((b - a for a, b in pairwise(kvah) if b >= a)) * 2
    assert row["half_hourly_meters"] == 1
    assert row["peak_kva_est"] == pytest.approx(float(peak), abs=1e-3)
    assert row["peak_at"].endswith("+05:30")
    # sorted by utilisation, nulls last
    utils = [i["utilisation_pct"] for i in items]
    known = [u for u in utils if u is not None]
    assert utils[: len(known)] == known and known == sorted(known, reverse=True)


def test_transformer_load_sort_by_code(full_api: Api) -> None:
    items = _get(full_api, f"{BASE}/transformers/load", sort="code", limit=100).json()["items"]
    codes = [i["code"] for i in items]
    assert codes == sorted(codes)
