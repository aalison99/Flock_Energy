from collections import Counter

import pytest

from tests.integration.conftest import Api

DT007 = "Z-01/C-01/D-07/SD-07/SS-07/F-007/DT-007"


def _walk(items: list[dict]) -> list[dict]:
    out: list[dict] = []
    for item in items:
        out.append(item)
        out.extend(_walk(item["children"]))
    return out


def test_empty_index_is_409_on_every_hierarchy_route(api: Api) -> None:
    for url in (
        "/api/v1/hierarchy",
        "/api/v1/hierarchy/node?id=Z-01",
        "/api/v1/hierarchy/node/meters?id=Z-01",
    ):
        r = api.client.get(url)
        assert r.status_code == 409, url
        assert r.json()["error"]["code"] == "index_not_ready"


def test_tree_depth_one_is_the_three_zones(synced_api: Api) -> None:
    body = synced_api.client.get("/api/v1/hierarchy?depth=1").json()
    assert [z["id"] for z in body["items"]] == ["Z-01", "Z-02", "Z-03"]
    assert all(z["children"] == [] and z["level"] == "zone" for z in body["items"])
    assert all(z["unplaced_count"] == 0 for z in body["items"])
    assert sum(z["meter_count"] for z in body["items"]) == 403
    assert set(body["items"][0]["status_breakdown"]) == {
        "installed",
        "faulty",
        "decommissioned",
        "unknown",
    }


def test_default_depth_is_two(synced_api: Api) -> None:
    zones = synced_api.client.get("/api/v1/hierarchy").json()["items"]
    levels = Counter(n["level"] for n in _walk(zones))
    assert levels == {"zone": 3, "circle": 6}


def test_full_depth_has_every_node(synced_api: Api) -> None:
    zones = synced_api.client.get("/api/v1/hierarchy?depth=7").json()["items"]
    levels = Counter(n["level"] for n in _walk(zones))
    assert [levels[k] for k in ("zone", "circle", "division", "subdivision")] == [3, 6, 30, 40]
    assert (levels["substation"], levels["feeder"], levels["dt"]) == (40, 40, 40)
    totals = Counter()
    for z in zones:
        totals.update(z["status_breakdown"])
    assert totals == {"installed": 238, "faulty": 90, "decommissioned": 75, "unknown": 0}


@pytest.mark.parametrize("depth", ["0", "8", "x"])
def test_bad_depth_is_422(synced_api: Api, depth: str) -> None:
    r = synced_api.client.get(f"/api/v1/hierarchy?depth={depth}")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


def test_node_detail_for_a_dt_path(synced_api: Api) -> None:
    r = synced_api.client.get("/api/v1/hierarchy/node", params={"id": DT007})
    assert r.status_code == 200
    body = r.json()
    assert (body["id"], body["level"], body["code"], body["name"]) == (
        DT007,
        "dt",
        "DT-007",
        "Sanganer DT 7",
    )
    assert [p["level"] for p in body["path"]] == [
        "zone",
        "circle",
        "division",
        "subdivision",
        "substation",
        "feeder",
        "dt",
    ]
    assert body["path"][-1]["id"] == DT007
    assert body["children"] == []
    assert body["meter_count"] == 13
    assert sum(body["status_breakdown"].values()) == 13
    assert body["alt_names"] == [
        {"name": "Old Malviya Nagar Xfmr", "meter_ids": ["J100400", "J100401", "J100402"]}
    ]


def test_node_detail_for_a_zone_lists_children_with_counts(synced_api: Api) -> None:
    body = synced_api.client.get("/api/v1/hierarchy/node?id=Z-01").json()
    assert body["path"] == [
        {
            "id": "Z-01",
            "level": "zone",
            "code": "Z-01",
            "name": "Jaipur Zone 1",
            "meter_count": body["meter_count"],
        }
    ]
    assert sum(c["meter_count"] for c in body["children"]) == body["meter_count"]
    assert all(c["level"] == "circle" for c in body["children"])


def test_unknown_node_is_404(synced_api: Api) -> None:
    for url in ("/api/v1/hierarchy/node?id=Z-09", "/api/v1/hierarchy/node/meters?id=Z-01/C-99"):
        r = synced_api.client.get(url)
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "not_found"
    message = synced_api.client.get("/api/v1/hierarchy/node?id=Z-09").json()["error"]["message"]
    assert message == "hierarchy node Z-09 not found"


@pytest.mark.parametrize("bad", ["", "z-01", "Z-1", "Z-01/", "Z-01/C-1", "DT-007", "Z-01/c-01"])
def test_bad_id_pattern_is_422(synced_api: Api, bad: str) -> None:
    for route in ("node", "node/meters"):
        r = synced_api.client.get(f"/api/v1/hierarchy/{route}", params={"id": bad})
        assert r.status_code == 422, (route, bad)


def test_missing_id_is_422(synced_api: Api) -> None:
    assert synced_api.client.get("/api/v1/hierarchy/node").status_code == 422


def test_node_meters_paging(synced_api: Api) -> None:
    url = "/api/v1/hierarchy/node/meters"
    first = synced_api.client.get(url, params={"id": DT007, "page_size": 5}).json()
    assert (first["total"], first["total_pages"], first["has_next"]) == (13, 3, True)
    assert [m["meter_id"] for m in first["items"]] == sorted(m["meter_id"] for m in first["items"])
    assert set(first["items"][0]) == {
        "meter_id",
        "serial_no",
        "make",
        "phase_type",
        "install_status",
        "dt_code",
    }
    last = synced_api.client.get(url, params={"id": DT007, "page_size": 5, "page": 3}).json()
    assert len(last["items"]) == 3
    assert last["has_next"] is False


def test_zone_meters_cover_the_subtree(synced_api: Api) -> None:
    ids: list[str] = []
    for zone in ("Z-01", "Z-02", "Z-03"):
        body = synced_api.client.get(
            "/api/v1/hierarchy/node/meters", params={"id": zone, "page_size": 200}
        ).json()
        ids += [m["meter_id"] for m in body["items"]]
    assert len(ids) == len(set(ids)) == 403


def test_hierarchy_never_calls_the_portal(synced_api: Api) -> None:
    synced_api.client.get("/api/v1/hierarchy?depth=7")
    synced_api.client.get("/api/v1/hierarchy/node", params={"id": DT007})
    assert synced_api.portal.calls == []
