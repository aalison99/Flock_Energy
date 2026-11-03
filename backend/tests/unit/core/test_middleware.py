import logging
import re

import pytest
from fastapi.testclient import TestClient


def test_generates_id(client: TestClient) -> None:
    rid = client.get("/api/v1/health").headers["X-Request-ID"]
    assert len(rid) == 32


def test_echoes_valid_id(client: TestClient) -> None:
    r = client.get("/api/v1/health", headers={"X-Request-ID": "abc-123._X"})
    assert r.headers["X-Request-ID"] == "abc-123._X"


@pytest.mark.parametrize("bad", ["a" * 200, "has space", "semi;colon"])
def test_replaces_invalid_id(client: TestClient, bad: str) -> None:
    rid = client.get("/api/v1/health", headers={"X-Request-ID": bad}).headers["X-Request-ID"]
    assert rid != bad
    assert len(rid) == 32


def test_access_log(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="urja.access"):
        r = client.get("/api/v1/health", headers={"X-Request-ID": "rid-1"})
    recs = [x for x in caplog.records if x.name == "urja.access"]
    assert len(recs) == 1
    rec = recs[0]
    assert (rec.method, rec.path, rec.status, rec.request_id) == (  # type: ignore[attr-defined]
        "GET",
        "/api/v1/health",
        r.status_code,
        "rid-1",
    )
    assert rec.duration_ms >= 0  # type: ignore[attr-defined]


def test_access_log_formatted_output_has_all_fields(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    from app.core.logging import make_formatter

    with caplog.at_level(logging.INFO, logger="urja.access"):
        client.get("/api/v1/health", headers={"X-Request-ID": "rid-42"})
    rec = next(x for x in caplog.records if x.name == "urja.access")
    text = make_formatter().format(rec)
    for needle in ("GET", "/api/v1/health", "200", "ms", "rid-42"):
        assert needle in text
    assert re.search(r"\d+(\.\d+)?ms", text)
