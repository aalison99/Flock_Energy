from app.domain.exceptions import UpstreamProtocolError, UpstreamUnavailableError
from tests.integration.conftest import Api


def test_list_envelope(api: Api) -> None:
    r = api.client.get("/api/v1/transformers?page_size=15")
    assert r.status_code == 200
    body = r.json()
    assert (body["page"], body["page_size"], body["total"]) == (1, 15, 40)
    assert (body["total_pages"], body["has_next"]) == (3, True)
    assert body["items"][0] == {
        "code": "DT-001",
        "name": "Malviya Nagar DT 1",
        "feeder_code": "F-001",
        "capacity_kva": 100,
    }
    codes = [t["code"] for t in body["items"]]
    assert codes == sorted(codes)
    assert r.headers["X-Request-ID"]


def test_last_page_has_no_next(api: Api) -> None:
    body = api.client.get("/api/v1/transformers?page=3&page_size=15").json()
    assert len(body["items"]) == 10
    assert body["has_next"] is False


def test_feeder_filter(api: Api) -> None:
    body = api.client.get("/api/v1/transformers?feeder=F-001").json()
    assert body["total"] >= 1
    assert {t["feeder_code"] for t in body["items"]} == {"F-001"}


def test_bad_feeder_pattern_is_422(api: Api) -> None:
    r = api.client.get("/api/v1/transformers?feeder=F-1")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


def test_page_size_too_big_is_422(api: Api) -> None:
    assert api.client.get("/api/v1/transformers?page_size=201").status_code == 422


def test_detail(api: Api) -> None:
    r = api.client.get("/api/v1/transformers/DT-002")
    assert r.status_code == 200
    assert r.json() == {
        "code": "DT-002",
        "name": "Mansarovar DT 2",
        "feeder_code": "F-002",
        "capacity_kva": 63,
    }


def test_detail_not_found(api: Api) -> None:
    r = api.client.get("/api/v1/transformers/DT-999")
    assert r.status_code == 404
    assert r.json()["error"] == {
        "code": "not_found",
        "message": "transformer DT-999 not found",
        "details": {},
    }
    assert r.headers["X-Request-ID"]


def test_bad_code_is_422(api: Api) -> None:
    assert api.client.get("/api/v1/transformers/DT-1").status_code == 422


def test_upstream_unavailable_is_503_with_retry_after(api: Api) -> None:
    api.portal.fail("list_transformers", UpstreamUnavailableError("down", retry_after_s=7))
    r = api.client.get("/api/v1/transformers")
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "upstream_unavailable"
    assert r.headers["Retry-After"] == "7"
    assert r.headers["X-Request-ID"]


def test_protocol_error_is_502(api: Api) -> None:
    api.portal.fail("list_transformers", UpstreamProtocolError("bad"))
    r = api.client.get("/api/v1/transformers/DT-001")
    assert r.status_code == 502
    assert r.json()["error"]["code"] == "upstream_protocol_error"
