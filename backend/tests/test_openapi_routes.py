"""The OpenAPI spec documents exactly the statuses each route can return."""

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

ROUTES: dict[tuple[str, str], set[str]] = {
    ("get", "/api/v1/health"): {"200"},
    ("get", "/api/v1/health/ready"): {"200", "503"},
    ("get", "/api/v1/geo/bbox"): {"200", "409", "422"},
    ("get", "/api/v1/geo/near"): {"200", "409", "422"},
    ("get", "/api/v1/meters"): {"200", "409", "422", "502", "503"},
    ("get", "/api/v1/meters/facets"): {"200", "409", "422"},
    ("get", "/api/v1/meters/{meter_id}"): {"200", "404", "422", "502", "503"},
    ("get", "/api/v1/meters/{meter_id}/readings"): {"200", "404", "422", "502", "503"},
    ("post", "/api/v1/sync"): {"202", "409", "422"},
    ("get", "/api/v1/sync/status"): {"200"},
    ("get", "/api/v1/transformers"): {"200", "422", "502", "503"},
    ("get", "/api/v1/transformers/{code}"): {"200", "404", "422", "502", "503"},
    ("get", "/api/v1/transformers/{code}/meters"): {"200", "404", "409", "422", "502", "503"},
}


@pytest.fixture
def spec(client: TestClient) -> dict[str, object]:
    data: dict[str, object] = client.get("/openapi.json").json()
    return data


def test_exact_route_list(spec: Any) -> None:
    assert {(m, p) for p, ops in spec["paths"].items() for m in ops} == set(ROUTES)


@pytest.mark.parametrize(("method", "path"), sorted(ROUTES))
def test_statuses_per_route(spec: Any, method: str, path: str) -> None:
    assert set(spec["paths"][path][method]["responses"]) == ROUTES[(method, path)]


def test_error_envelope_referenced_and_no_default_validation_model(spec: dict[str, object]) -> None:
    text = json.dumps(spec)
    assert "#/components/schemas/ErrorResponse" in text
    assert "HTTPValidationError" not in text
    assert "ValidationError" not in json.dumps(spec["components"]).replace("validation_error", "")


def test_readiness_503_uses_the_readiness_body(
    spec: dict[
        str, dict[str, dict[str, dict[str, dict[str, dict[str, dict[str, dict[str, str]]]]]]]
    ],
) -> None:
    ref = spec["paths"]["/api/v1/health/ready"]["get"]["responses"]["503"]["content"][
        "application/json"
    ]["schema"]["$ref"]
    assert ref.endswith("/ReadinessResponse")


def _schemas(spec: Any) -> dict[str, Any]:
    out: dict[str, Any] = spec["components"]["schemas"]
    return out


def _enum_of(spec: Any, model: str, field: str) -> list[str]:
    schemas = _schemas(spec)
    prop = schemas[model]["properties"][field]
    for option in [prop, *prop.get("anyOf", [])]:
        ref = option.get("$ref")
        target = schemas[ref.rsplit("/", 1)[1]] if ref else option
        if "enum" in target:
            found: list[str] = target["enum"]
            return found
    raise AssertionError(f"{model}.{field} has no enum")


def test_enum_values_are_in_the_spec(spec: Any) -> None:
    phase = ["single", "three", "unknown"]
    status = ["installed", "faulty", "decommissioned", "unknown"]
    levels = ["zone", "circle", "division", "subdivision", "substation", "feeder", "dt"]
    for model in ("MeterSummary", "MeterDetail"):
        assert _enum_of(spec, model, "phase_type") == phase
        assert _enum_of(spec, model, "install_status") == status
    assert _enum_of(spec, "MeterDetail", "install_type") == [
        "whole_current",
        "ct_operated",
        "unknown",
    ]
    assert _enum_of(spec, "HierarchyNodeOut", "level") == levels
    assert _enum_of(spec, "PortalReadiness", "breaker") == ["closed", "open", "half_open"]


def test_operation_ids(spec: Any) -> None:
    ids = {(m, p): op["operationId"] for p, ops in spec["paths"].items() for m, op in ops.items()}
    assert ids == {
        ("get", "/api/v1/health"): "getHealth",
        ("get", "/api/v1/health/ready"): "getReadiness",
        ("get", "/api/v1/geo/bbox"): "findMetersInBox",
        ("get", "/api/v1/geo/near"): "findMetersNear",
        ("get", "/api/v1/meters"): "listMeters",
        ("get", "/api/v1/meters/facets"): "getMeterFacets",
        ("get", "/api/v1/meters/{meter_id}"): "getMeter",
        ("get", "/api/v1/meters/{meter_id}/readings"): "getMeterReadings",
        ("post", "/api/v1/sync"): "startSync",
        ("get", "/api/v1/sync/status"): "getSyncStatus",
        ("get", "/api/v1/transformers"): "listTransformers",
        ("get", "/api/v1/transformers/{code}"): "getTransformer",
        ("get", "/api/v1/transformers/{code}/meters"): "listTransformerMeters",
    }


def test_retry_after_header_documented_on_error_503s(spec: Any) -> None:
    for (method, path), statuses in ROUTES.items():
        if path.endswith("/ready") or "503" not in statuses:
            continue
        header = spec["paths"][path][method]["responses"]["503"]["headers"]["Retry-After"]
        assert header["schema"] == {"type": "integer"}
        assert header["description"]


def test_every_field_and_param_is_described(spec: Any) -> None:
    for name, schema in _schemas(spec).items():
        for field, prop in schema.get("properties", {}).items():
            assert prop.get("description"), f"{name}.{field}"
    for ops in spec["paths"].values():
        for op in ops.values():
            for param in op.get("parameters", []):
                assert param.get("description"), param["name"]


def test_examples_validate_against_their_models() -> None:
    from app.api.v1.schemas.geo import BBoxResponse
    from app.api.v1.schemas.meters import FacetsResponse, MeterDetail, MeterSummary
    from app.api.v1.schemas.readings import ReadingSeriesResponse
    from app.api.v1.schemas.sync import SyncRequest, SyncRunOut, SyncStatusResponse
    from app.api.v1.schemas.transformers import TransformerOut

    for model in (
        MeterDetail,
        MeterSummary,
        FacetsResponse,
        BBoxResponse,
        TransformerOut,
        ReadingSeriesResponse,
        SyncRequest,
        SyncRunOut,
        SyncStatusResponse,
    ):
        extra: Any = model.model_config["json_schema_extra"]
        model.model_validate(extra["example"])


def test_reading_enums_are_in_the_spec(spec: Any) -> None:
    assert _enum_of(spec, "ReadingSeriesResponse", "resolution") == ["raw", "hourly", "daily"]
    assert _enum_of(spec, "ReadingSeriesResponse", "interval_kind") == [
        "half_hourly",
        "daily",
        "unknown",
    ]


def test_sync_enums_and_statuses_are_in_the_spec(spec: Any) -> None:
    assert _enum_of(spec, "SyncRunOut", "status") == ["running", "succeeded", "failed"]
    assert _enum_of(spec, "SyncRunOut", "strategy") == ["export", "crawl"]
    post = spec["paths"]["/api/v1/sync"]["post"]
    assert "requestBody" in post
    assert post["requestBody"].get("required") is not True  # the body is optional


def test_breaker_literal_matches_the_breaker_enum(spec: Any) -> None:
    from app.portal.interfaces import BreakerState

    assert set(_enum_of(spec, "PortalReadiness", "breaker")) == {s.value for s in BreakerState}


def test_meter_enums_filters_and_source_are_in_the_spec(spec: Any) -> None:
    assert _enum_of(spec, "MetaOut", "source") == ["portal", "index"]
    params = {p["name"]: p for p in spec["paths"]["/api/v1/meters"]["get"]["parameters"]}
    expected = {
        "q", "status", "make", "phase", "install_type", "dt", "feeder", "substation",
        "subdivision", "division", "circle", "zone", "has_geo", "sort", "page", "page_size",
    }  # fmt: skip
    assert set(params) == expected
    schemas = _schemas(spec)
    assert params["sort"]["schema"]["$ref"].endswith("/MeterSort")
    assert schemas["MeterSort"]["enum"] == ["meter_id", "-meter_id", "make", "status"]
    status_array = params["status"]["schema"]["anyOf"][0]
    assert status_array["maxItems"] == 10
    assert schemas["InstallStatus"]["enum"] == [
        "installed",
        "faulty",
        "decommissioned",
        "unknown",
    ]
    assert params["dt"]["schema"]["anyOf"][0]["pattern"] == r"^DT-\d{3}$"
    facet_params = {p["name"] for p in spec["paths"]["/api/v1/meters/facets"]["get"]["parameters"]}
    assert facet_params == (expected - {"page", "page_size"}) | {"field"}
    geo_near = {p["name"] for p in spec["paths"]["/api/v1/geo/near"]["get"]["parameters"]}
    assert {"lat", "lng", "radius_km", "limit", "q", "dt"} <= geo_near
