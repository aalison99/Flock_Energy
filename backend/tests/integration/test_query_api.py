"""The M6 query layer end to end: real app, real SyncService into SQLite, portal faked."""

import asyncio
from typing import Any

import pytest

from app.core.deps import get_meter_catalog
from app.domain.models import Meter
from app.portal.fake import FakePortalClient
from app.repositories.interfaces import MeterQuery
from app.services.catalogs.live_catalog import LiveMeterCatalog
from app.services.geo import haversine_km
from tests.integration.conftest import Api
from tests.support import meter_oracle
from tests.support.portal_emulator import FIXTURES

ALL: list[Meter] = asyncio.run(FakePortalClient(FIXTURES).bulk_export())
SINGLE_DT7 = {"dt": "DT-007", "phase": "single"}


def _ids(api: Api, query: str) -> list[str]:
    ids: list[str] = []
    page = 1
    while True:
        r = api.client.get(f"/api/v1/meters?page_size=200&page={page}&{query}")
        assert r.status_code == 200, r.text
        body = r.json()
        ids += [m["meter_id"] for m in body["items"]]
        if not body["has_next"]:
            return ids
        page += 1


def _expected(**fields: Any) -> list[str]:
    return [m.meter_id for m in meter_oracle.search(ALL, MeterQuery(**fields))]


# --- wirings -----------------------------------------------------------------------------------


@pytest.fixture(params=["prefer-index", "live-only"])
def wired(request: pytest.FixtureRequest, synced_api: Api) -> tuple[Api, str]:
    """Both catalog wirings over the same synced app: swapping is one dependency override."""
    if request.param == "live-only":
        portal = synced_api.portal
        synced_api.app.dependency_overrides[get_meter_catalog] = lambda: LiveMeterCatalog(portal)
    return synced_api, request.param


def test_q_list_is_identical_under_both_wirings(wired: tuple[Api, str]) -> None:
    api, _ = wired
    body = api.client.get("/api/v1/meters?q=se33962").json()
    assert body["total"] == 1
    assert body["items"][0]["meter_id"] == "J100000"
    assert api.client.get("/api/v1/meters?page=9").json()["items"][0]["meter_id"] == "J100400"


def test_detail_source_follows_the_wiring(wired: tuple[Api, str]) -> None:
    api, name = wired
    body = api.client.get("/api/v1/meters/J100000").json()
    assert body["meter_id"] == "J100000"
    assert body["geo"] == {"lat": 26.938961002479868, "lng": 75.83095696146852}
    assert body["meta"]["source"] == ("index" if name == "prefer-index" else "portal")
    portal_calls = [n for n, _ in api.portal.calls]
    assert ("get_geo" in portal_calls) is (name == "live-only")


def test_live_only_wiring_rejects_rich_filters_with_422(wired: tuple[Api, str]) -> None:
    api, name = wired
    r = api.client.get("/api/v1/meters?status=faulty")
    assert r.status_code == (200 if name == "prefer-index" else 422)


# --- filters, sort, paging --------------------------------------------------------------------


def test_detail_from_the_index_has_synced_at_meta(synced_api: Api) -> None:
    body = synced_api.client.get("/api/v1/meters/J100000").json()
    assert body["meta"]["source"] == "index"
    assert body["meta"]["stale"] is False
    assert body["meta"]["fetched_at"].endswith("Z") or "+" in body["meta"]["fetched_at"]
    assert len(body["hierarchy"]) == 7
    assert synced_api.portal.calls == []


def test_unknown_meter_is_404_from_the_index(synced_api: Api) -> None:
    assert synced_api.client.get("/api/v1/meters/J999999").status_code == 404


@pytest.mark.parametrize(
    ("query", "fields"),
    [
        ("status=faulty", {"status": ("faulty",)}),
        ("status=faulty&status=decommissioned", {"status": ("faulty", "decommissioned")}),
        ("make=HPL&make=L%26T", {"make": ("HPL", "L&T")}),
        ("phase=three&install_type=ct_operated", {"phase": "three", "install_type": "ct_operated"}),
        ("dt=DT-007", {"dt": "DT-007"}),
        ("feeder=F-007", {"feeder": "F-007"}),
        ("division=D-01", {"division": "D-01"}),
        ("zone=Z-02&circle=C-01", {"zone": "Z-02", "circle": "C-01"}),
        ("has_geo=true", {"has_geo": True}),
        ("q=j1003&status=installed", {"q": "j1003", "status": ("installed",)}),
        ("sort=-meter_id&make=Genus", {"sort": "-meter_id", "make": ("Genus",)}),
        ("sort=make", {"sort": "make"}),
        ("sort=status&phase=single", {"sort": "status", "phase": "single"}),
    ],
)
def test_filters_and_sorts_match_the_oracle(
    synced_api: Api, query: str, fields: dict[str, Any]
) -> None:
    assert _ids(synced_api, query) == _expected(**fields)


def test_division_matches_the_code_wherever_it_occurs(synced_api: Api) -> None:
    assert len(_ids(synced_api, "division=D-01")) == 40


def test_total_and_paging_under_a_filter(synced_api: Api) -> None:
    body = synced_api.client.get("/api/v1/meters?dt=DT-007&page_size=5&page=3").json()
    assert (body["total"], body["total_pages"], len(body["items"]), body["has_next"]) == (
        13,
        3,
        3,
        False,
    )


@pytest.mark.parametrize(
    "query",
    [
        "status=bogus",
        "phase=bogus",
        "sort=bogus",
        "dt=DT-1",
        "feeder=F-1",
        "has_geo=maybe",
        "&".join(["make=a"] * 11),
        "&".join(["status=faulty"] * 11),
    ],
)
def test_bad_filter_values_are_422(synced_api: Api, query: str) -> None:
    r = synced_api.client.get(f"/api/v1/meters?{query}")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize(
    "name", ["make", "zone", "circle", "division", "subdivision", "substation"]
)
def test_overlong_code_filters_are_422(synced_api: Api, name: str) -> None:
    assert synced_api.client.get(f"/api/v1/meters?{name}={'x' * 33}").status_code == 422
    assert synced_api.client.get(f"/api/v1/meters?{name}={'x' * 32}").status_code == 200


def test_ten_repeated_values_are_fine(synced_api: Api) -> None:
    assert synced_api.client.get("/api/v1/meters?" + "&".join(["make=HPL"] * 10)).status_code == 200


# --- facets -----------------------------------------------------------------------------------


def test_facets_for_the_full_set(synced_api: Api) -> None:
    r = synced_api.client.get("/api/v1/meters/facets")
    assert r.status_code == 200
    facets = r.json()["facets"]
    assert set(facets) == {"status", "make", "phase", "install_type", "dt"}
    assert facets["status"] == {"installed": 238, "faulty": 90, "decommissioned": 75}
    assert facets["make"] == {"HPL": 90, "Genus": 88, "Secure": 85, "Allied": 76, "L&T": 64}
    assert facets["phase"] == {"single": 277, "three": 126}
    assert facets["install_type"] == {"whole_current": 205, "ct_operated": 198}
    assert facets["dt"]["DT-007"] == 13
    assert sum(facets["dt"].values()) == 403
    assert len(facets["dt"]) == 40


def test_facets_do_not_apply_their_own_filter(synced_api: Api) -> None:
    facets = synced_api.client.get(
        "/api/v1/meters/facets?status=faulty&make=HPL&field=status&field=make"
    ).json()["facets"]
    assert set(facets) == {"status", "make"}
    query = MeterQuery(status=("faulty",), make=("HPL",))
    assert facets["status"] == meter_oracle.facet(ALL, query, "status")
    assert facets["make"] == meter_oracle.facet(ALL, query, "make")
    assert len(facets["status"]) == 3  # other statuses stay visible as alternatives
    assert len(facets["make"]) == 5


def test_facets_under_a_dt_filter_with_zero_counts_omitted(synced_api: Api) -> None:
    facets = synced_api.client.get("/api/v1/meters/facets?dt=DT-007&field=phase&field=dt").json()[
        "facets"
    ]
    assert sum(facets["phase"].values()) == 13
    assert len(facets["dt"]) == 40  # the dt facet ignores the dt filter
    assert all(count > 0 for count in facets["phase"].values())


def test_facets_route_is_not_captured_by_the_detail_route(synced_api: Api) -> None:
    r = synced_api.client.get("/api/v1/meters/facets")
    assert r.status_code == 200
    assert "facets" in r.json()


def test_facets_bad_field_is_422(synced_api: Api) -> None:
    assert synced_api.client.get("/api/v1/meters/facets?field=bogus").status_code == 422


# --- geo --------------------------------------------------------------------------------------

JAIPUR = (26.9124, 75.7873)


def test_near_matches_a_brute_force_haversine(synced_api: Api) -> None:
    r = synced_api.client.get("/api/v1/geo/near?lat=26.9124&lng=75.7873&radius_km=5&limit=200")
    assert r.status_code == 200
    items = r.json()["items"]
    from app.domain.models import GeoPoint

    centre = GeoPoint(*JAIPUR)
    expected = sorted(
        (haversine_km(centre, m.geo), m.meter_id)
        for m in ALL
        if m.geo and haversine_km(centre, m.geo) <= 5
    )
    assert [i["meter"]["meter_id"] for i in items] == [mid for _, mid in expected]
    assert [i["distance_km"] for i in items] == [round(d, 3) for d, _ in expected]
    first = items[0]
    assert set(first) == {"meter", "lat", "lng", "distance_km"}
    assert set(first["meter"]) == {
        "meter_id",
        "serial_no",
        "make",
        "phase_type",
        "install_status",
        "dt_code",
    }


def test_near_with_filters_and_limit(synced_api: Api) -> None:
    r = synced_api.client.get(
        "/api/v1/geo/near?lat=26.9124&lng=75.7873&radius_km=50&limit=3&make=HPL"
    )
    items = r.json()["items"]
    assert len(items) == 3
    assert {i["meter"]["make"] for i in items} == {"HPL"}
    assert [i["distance_km"] for i in items] == sorted(i["distance_km"] for i in items)


@pytest.mark.parametrize(
    "query",
    [
        "lat=91&lng=0",
        "lat=0&lng=181",
        "lat=0&lng=0&radius_km=0",
        "lat=0&lng=0&radius_km=50.1",
        "lat=0&lng=0&limit=0",
        "lat=0&lng=0&limit=201",
        "lng=0",
    ],
)
def test_near_validation_is_422(synced_api: Api, query: str) -> None:
    assert synced_api.client.get(f"/api/v1/geo/near?{query}").status_code == 422


def test_bbox_lists_points_and_flags_truncation(synced_api: Api) -> None:
    r = synced_api.client.get(
        "/api/v1/geo/bbox?min_lat=-90&min_lng=-180&max_lat=90&max_lng=180&limit=100"
    )
    body = r.json()
    assert body["truncated"] is True
    assert len(body["items"]) == 100
    assert set(body["items"][0]) == {"meter_id", "lat", "lng", "install_status", "dt_code"}
    full = synced_api.client.get(
        "/api/v1/geo/bbox?min_lat=-90&min_lng=-180&max_lat=90&max_lng=180"
    ).json()
    assert (len(full["items"]), full["truncated"]) == (403, False)


def test_bbox_with_filter(synced_api: Api) -> None:
    body = synced_api.client.get(
        "/api/v1/geo/bbox?min_lat=-90&min_lng=-180&max_lat=90&max_lng=180&dt=DT-007"
    ).json()
    assert {i["dt_code"] for i in body["items"]} == {"DT-007"}
    assert len(body["items"]) == 13


def test_bbox_inverted_is_422_and_limit_bounds(synced_api: Api) -> None:
    base = "/api/v1/geo/bbox?min_lng=0&max_lng=1"
    inverted = synced_api.client.get(f"{base}&min_lat=5&max_lat=1")
    assert inverted.status_code == 422
    assert inverted.json()["error"]["code"] == "validation_error"
    assert synced_api.client.get(f"{base}&min_lat=0&max_lat=1&limit=2001").status_code == 422


# --- transformers -----------------------------------------------------------------------------


def test_transformer_meter_counts_and_meters(synced_api: Api) -> None:
    dt = synced_api.client.get("/api/v1/transformers/DT-007").json()
    assert dt["meter_count"] == 13
    listed = synced_api.client.get("/api/v1/transformers?page_size=200").json()["items"]
    assert sum(t["meter_count"] for t in listed) == 403
    r = synced_api.client.get("/api/v1/transformers/DT-007/meters")
    body = r.json()
    assert (r.status_code, body["total"], len(body["items"])) == (200, 13, 13)
    assert {m["dt_code"] for m in body["items"]} == {"DT-007"}
    paged = synced_api.client.get("/api/v1/transformers/DT-007/meters?page=2&page_size=10").json()
    assert (len(paged["items"]), paged["has_next"]) == (3, False)


def test_transformer_meters_unknown_dt_is_404_and_bad_code_422(synced_api: Api) -> None:
    assert synced_api.client.get("/api/v1/transformers/DT-999/meters").status_code == 404
    assert synced_api.client.get("/api/v1/transformers/DT-7/meters").status_code == 422


# --- empty index ------------------------------------------------------------------------------


def test_empty_index_serves_q_live(api: Api) -> None:
    body = api.client.get("/api/v1/meters?q=se33962").json()
    assert body["total"] == 1
    assert api.client.get("/api/v1/meters/J100000").json()["meta"]["source"] == "portal"


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/meters?status=faulty",
        "/api/v1/meters?sort=make",
        "/api/v1/meters/facets",
        "/api/v1/geo/near?lat=26.9&lng=75.8",
        "/api/v1/geo/bbox?min_lat=0&min_lng=0&max_lat=1&max_lng=1",
        "/api/v1/transformers/DT-007/meters",
    ],
)
def test_empty_index_gives_a_409_envelope(api: Api, path: str) -> None:
    r = api.client.get(path)
    assert r.status_code == 409
    error = r.json()["error"]
    assert error["code"] == "index_not_ready"
    assert error["message"]
    assert r.headers["X-Request-ID"]


def test_empty_index_transformers_have_null_meter_count(api: Api) -> None:
    assert api.client.get("/api/v1/transformers/DT-007").json()["meter_count"] is None
    assert api.client.get("/api/v1/transformers").json()["items"][0]["meter_count"] is None
