from tests.integration.conftest import Api

URL = "/api/v1/data-quality"
EXPECTED_SUMMARY = {
    "name_conflict": 1,
    "blank_field_repaired": 22,
    "unplaced_meter": 0,
    "parent_conflict": 0,
    "dt_code_mismatch": 0,
    "unknown_dt": 0,
    "dt_without_meters": 0,
    "dt_feeder_mismatch": 0,
    "missing_geo": 0,
    "geo_outlier": 0,
}


def test_empty_index_is_409(api: Api) -> None:
    r = api.client.get(URL)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "index_not_ready"


def test_summary_for_the_fixtures(synced_api: Api) -> None:
    body = synced_api.client.get(URL).json()
    assert body["summary"] == EXPECTED_SUMMARY
    assert [c["id"] for c in body["checks"]] == list(EXPECTED_SUMMARY)
    assert set(body["checks"][0]) == {"id", "severity", "description"}
    assert (body["page"], body["page_size"], body["total"]) == (1, 50, 23)
    assert (body["total_pages"], body["has_next"]) == (1, False)


def test_items_ordered_warning_before_info(synced_api: Api) -> None:
    items = synced_api.client.get(URL, params={"page_size": 200}).json()["items"]
    assert [i["check"] for i in items][:1] == ["name_conflict"]
    assert {i["severity"] for i in items[1:]} == {"info"}


def test_dt_007_issue_shape(synced_api: Api) -> None:
    body = synced_api.client.get(URL, params={"check": "name_conflict"}).json()
    (issue,) = body["items"]
    assert issue["severity"] == "warning"
    assert issue["entity"] == "node"
    assert issue["entity_id"] == "Z-01/C-01/D-07/SD-07/SS-07/F-007/DT-007"
    assert issue["evidence"] == {
        "canonical": "Sanganer DT 7",
        "canonical_source": "dt_list",
        "aliases": [
            {"name": "Old Malviya Nagar Xfmr", "meter_ids": ["J100400", "J100401", "J100402"]}
        ],
    }


def test_filters_leave_the_summary_alone(synced_api: Api) -> None:
    body = synced_api.client.get(
        URL, params={"check": "blank_field_repaired", "page_size": 10}
    ).json()
    assert body["summary"] == EXPECTED_SUMMARY
    assert (body["total"], body["total_pages"], body["has_next"]) == (22, 3, True)
    assert {i["check"] for i in body["items"]} == {"blank_field_repaired"}
    by_severity = synced_api.client.get(URL, params={"severity": "info"}).json()
    assert by_severity["total"] == 22
    assert synced_api.client.get(URL, params={"severity": "error"}).json()["total"] == 0
    both = synced_api.client.get(URL, params={"check": "name_conflict", "severity": "info"}).json()
    assert both["total"] == 0


def test_unknown_check_is_422(synced_api: Api) -> None:
    r = synced_api.client.get(URL, params={"check": "nope"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"
    assert "name_conflict" in r.json()["error"]["details"]["valid"]


def test_bad_severity_or_paging_is_422(synced_api: Api) -> None:
    assert synced_api.client.get(URL, params={"severity": "fatal"}).status_code == 422
    assert synced_api.client.get(URL, params={"page_size": 201}).status_code == 422
    assert synced_api.client.get(URL, params={"page": 0}).status_code == 422
