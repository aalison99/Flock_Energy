"""Every parser: happy path from its fixture, malformed input, and embedded signals."""

import json
import logging
from datetime import timedelta
from pathlib import Path

import pytest

from app.domain.exceptions import (
    NotFoundError,
    UpstreamAuthError,
    UpstreamProtocolError,
)
from app.domain.models import GeoPoint, InstallStatus, Meter, Reading, Transformer
from app.portal.errors import SessionExpired, SignatureRejected
from app.portal.interfaces import PortalPage
from app.portal.parsers.registry import ParserRegistry, PayloadKind, default_registry

FIX = Path(__file__).parents[2] / "fixtures" / "portal"
registry = default_registry()


def raw(rel: str) -> bytes:
    return (FIX / rel).read_bytes()


def test_search_page() -> None:
    page = registry.parse(PayloadKind.SEARCH_PAGE, raw("meters/search_page1.json"))
    assert isinstance(page, PortalPage)
    assert len(page.items) == 20
    assert (page.total, page.page, page.page_size) == (403, 1, 20)
    assert all(isinstance(m, Meter) for m in page.items)
    assert page.items[0].meter_id == "J100000"
    assert page.items[0].install_status is InstallStatus.DECOMMISSIONED


def test_search_past_end() -> None:
    page = registry.parse(PayloadKind.SEARCH_PAGE, raw("meters/search_page22_past_end.json"))
    assert isinstance(page, PortalPage)
    assert page.items == () and page.total == 403


def test_dt_page() -> None:
    page = registry.parse(PayloadKind.DT_PAGE, raw("dts/page1.json"))
    assert isinstance(page, PortalPage)
    assert len(page.items) == 20
    first = page.items[0]
    assert isinstance(first, Transformer)
    assert (first.code, first.capacity_kva, first.feeder_code) == ("DT-001", 100, "F-001")


def test_meter_detail_legacy_and_v2() -> None:
    legacy = registry.parse(PayloadKind.METER_DETAIL, raw("meters/detail_legacy_J100000.json"))
    assert isinstance(legacy, Meter)
    assert (legacy.serial_no, legacy.build, legacy.geo) == ("SE33962", "legacy", None)
    v2 = registry.parse(PayloadKind.METER_DETAIL, raw("meters/detail_v2_J100086.json"))
    assert isinstance(v2, Meter)
    assert (v2.serial_no, v2.build, v2.dt_code) == ("SE82374", "v2", "DT-007")


def test_geo() -> None:
    assert registry.parse(PayloadKind.GEO, raw("meters/geo_J100000.json")) == GeoPoint(
        26.938961002479868, 75.83095696146852
    )
    assert registry.parse(PayloadKind.GEO, b'{"data":null}') is None


def test_energy_sorted() -> None:
    out = registry.parse(PayloadKind.ENERGY, raw("energy/halfhourly_J100000.json"))
    assert isinstance(out, list) and len(out) == 337
    assert all(isinstance(r, Reading) for r in out)
    ats = [r.at for r in out]
    assert ats == sorted(ats)
    shuffled = json.dumps(
        {
            "data": [
                {"timestamp": "02/01/2026 00:00", "kwh": "2", "kvah": "2", "voltR": "1"},
                {"timestamp": "01/01/2026 00:00", "kwh": "1", "kvah": "1", "voltR": ""},
            ]
        }
    ).encode()
    got = registry.parse(PayloadKind.ENERGY, shuffled)
    assert isinstance(got, list)
    assert got[0].kwh_register == 1.0 and got[1].at - got[0].at == timedelta(days=1)


def test_export() -> None:
    out = registry.parse(PayloadKind.EXPORT, raw("export/export_page1.json"))
    assert isinstance(out, list) and len(out) == 403


def test_keys() -> None:
    assert registry.parse(PayloadKind.KEYS, raw("export/keys.json")) == "test-signing-secret"


def test_login_action() -> None:
    assert registry.parse(PayloadKind.LOGIN_ACTION, raw("auth/login_ok.json")) is None
    with pytest.raises(UpstreamAuthError) as ei:
        registry.parse(PayloadKind.LOGIN_ACTION, raw("auth/login_bad_password.json"))
    assert ei.value.message == "Invalid email or password."


JSON_KINDS = [
    PayloadKind.SEARCH_PAGE,
    PayloadKind.DT_PAGE,
    PayloadKind.GEO,
    PayloadKind.ENERGY,
    PayloadKind.EXPORT,
    PayloadKind.KEYS,
]


@pytest.mark.parametrize("kind", JSON_KINDS)
def test_shared_signals(kind: PayloadKind) -> None:
    with pytest.raises(SessionExpired):
        registry.parse(kind, raw("auth/portal_unauthorized.json"))
    with pytest.raises(NotFoundError, match="Meter not found"):
        registry.parse(kind, raw("meters/portal_not_found.json"))
    with pytest.raises(SignatureRejected):
        registry.parse(kind, raw("export/signature_invalid.json"))


@pytest.mark.parametrize("kind", list(PayloadKind))
def test_malformed_json(kind: PayloadKind) -> None:
    with pytest.raises(UpstreamProtocolError, match=f"^{kind.name}: "):
        registry.parse(kind, b"{not json")
    with pytest.raises(UpstreamProtocolError, match=f"^{kind.name}: "):
        registry.parse(kind, b"[]")


@pytest.mark.parametrize("kind", list(PayloadKind))
def test_missing_key_or_wrong_type(kind: PayloadKind) -> None:
    for body in (b"{}", b'{"data": 5, "type": "data", "nodes": 5}', b'{"data": [5]}'):
        with pytest.raises(UpstreamProtocolError, match=f"^{kind.name}: "):
            registry.parse(kind, body)


def test_bad_row_is_protocol_error() -> None:
    body = b'{"data":[{"meterId":"J1"}],"total":1,"page":1,"pageSize":20}'
    with pytest.raises(UpstreamProtocolError, match=r"^SEARCH_PAGE: "):
        registry.parse(PayloadKind.SEARCH_PAGE, body)


def test_detail_signals() -> None:
    with pytest.raises(SessionExpired):
        registry.parse(PayloadKind.METER_DETAIL, raw("auth/sveltekit_redirect_to_login.json"))
    with pytest.raises(NotFoundError):
        registry.parse(PayloadKind.METER_DETAIL, raw("meters/detail_not_found.json"))
    with pytest.raises(SessionExpired):
        registry.parse(PayloadKind.METER_DETAIL, raw("auth/portal_unauthorized.json"))


def test_login_other_redirect_and_unknown_type() -> None:
    with pytest.raises(UpstreamProtocolError):
        registry.parse(PayloadKind.LOGIN_ACTION, b'{"type":"weird"}')
    with pytest.raises(UpstreamProtocolError):
        registry.parse(PayloadKind.LOGIN_ACTION, b'{"type":"failure","data":"[1]"}')


def test_registry_rules() -> None:
    reg = default_registry()
    parser = reg.get(PayloadKind.KEYS)
    with pytest.raises(ValueError):
        reg.register(parser)
    with pytest.raises(KeyError):
        ParserRegistry().get(PayloadKind.KEYS)
    assert {k for k in PayloadKind if reg.get(k)} == set(PayloadKind)


def test_redirect_elsewhere_is_not_session_expired() -> None:
    with pytest.raises(UpstreamProtocolError):
        registry.parse(PayloadKind.METER_DETAIL, b'{"type":"redirect","location":"/elsewhere"}')


def test_unexpected_error_is_logged_with_traceback(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def boom(_d: object) -> object:
        raise TypeError("secret payload data")

    monkeypatch.setattr("app.portal.mappers.meter_from_summary", boom)
    with caplog.at_level("WARNING"), pytest.raises(UpstreamProtocolError) as ei:
        registry.parse(PayloadKind.SEARCH_PAGE, raw("meters/search_page1.json"))
    assert "secret" not in ei.value.message
    records = [r for r in caplog.records if r.levelname == "WARNING" and r.exc_info]
    assert records and records[0].exc_info is not None
    assert records[0].exc_info[0] is TypeError


def test_injected_detail_registry_is_used() -> None:
    from app.portal.parsers.detail_formats import DetailFormatRegistry
    from app.portal.parsers.meter_detail import MeterDetailParser

    class Dummy:
        build = "dummy"

        def matches(self, detail: dict[str, object]) -> bool:
            return "dummy" in detail

        def fields(self, detail: dict[str, object]) -> dict[str, str]:
            return {
                "meter_id": "JX",
                "serial_no": "S",
                "make": "M",
                "phase_type": "three",
                "install_status": "Faulty",
                "install_type": "CT Operated",
            }

    formats = DetailFormatRegistry()
    formats.register(Dummy())
    body = json.dumps(
        {
            "type": "data",
            "nodes": [
                None,
                None,
                {
                    "type": "data",
                    "data": [
                        {"detail": 1, "hierarchy": 2},
                        {"dummy": 3},
                        {
                            k: 3
                            for k in (
                                "Zone",
                                "Circle",
                                "Division",
                                "Subdivision",
                                "Sub Station",
                                "Feeder",
                                "DT",
                            )
                        },
                        "Name (C-1)",
                    ],
                },
            ],
        }
    ).encode()
    meter = MeterDetailParser(formats).parse(body)
    assert isinstance(meter, Meter)
    assert (meter.meter_id, meter.build) == ("JX", "dummy")


def _energy(*rows: dict[str, object]) -> bytes:
    return json.dumps({"data": list(rows)}).encode()


def _row(day: int, kwh: object, kvah: object) -> dict[str, object]:
    return {"timestamp": f"{day:02d}/01/2026 00:00", "kwh": kwh, "kvah": kvah, "voltR": "230"}


@pytest.mark.parametrize(
    ("kwh", "kvah"), [("", "2"), ("   ", "2"), (None, "2"), ("2", ""), ("2", None), ("", "")]
)
def test_energy_skips_rows_with_blank_registers(
    kwh: object, kvah: object, caplog: pytest.LogCaptureFixture
) -> None:
    raw_body = _energy(_row(1, "1", "1"), _row(2, kwh, kvah), _row(3, "3", "3"))
    with caplog.at_level(logging.WARNING):
        got = registry.parse(PayloadKind.ENERGY, raw_body)
    assert isinstance(got, list)
    assert [r.kwh_register for r in got] == [1.0, 3.0]  # day 2 became a gap
    warnings_ = [r.getMessage() for r in caplog.records if "skipped" in r.getMessage()]
    assert warnings_ == ["energy payload: skipped 1 row(s) with blank registers"]


def test_energy_missing_key_counts_as_blank() -> None:
    row = {"timestamp": "02/01/2026 00:00", "kvah": "2"}  # no kwh key at all
    got = registry.parse(PayloadKind.ENERGY, _energy(_row(1, "1", "1"), row))
    assert isinstance(got, list) and len(got) == 1


def test_energy_all_blank_is_an_empty_list_not_an_error(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        got = registry.parse(PayloadKind.ENERGY, _energy(_row(1, "", ""), _row(2, None, "")))
    assert got == []
    assert "skipped 2 row(s)" in caplog.text


def test_energy_without_blank_rows_logs_nothing(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        registry.parse(PayloadKind.ENERGY, _energy(_row(1, "1", "1")))
    assert "skipped" not in caplog.text


@pytest.mark.parametrize(
    "bad",
    [
        _row(1, "abc", "1"),
        _row(1, "1", "abc"),
        {"timestamp": "not a date", "kwh": "1", "kvah": "1"},
        {"timestamp": "01/01/2026 00:00", "kwh": "1", "kvah": "1", "voltR": "oops"},
    ],
)
def test_energy_other_malformed_values_still_raise(bad: dict[str, object]) -> None:
    with pytest.raises(UpstreamProtocolError):
        registry.parse(PayloadKind.ENERGY, _energy(_row(2, "1", "1"), bad))
