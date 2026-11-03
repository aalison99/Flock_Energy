"""Mapper rules: node splitting, enum normalisation, numbers, timestamps, meter shapes."""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.domain.exceptions import UpstreamProtocolError
from app.domain.models import GeoPoint, InstallStatus, InstallType, NodeRef, PhaseType
from app.portal import mappers

IST = ZoneInfo("Asia/Kolkata")


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Jaipur Zone 1 (Z-01)", NodeRef("Z-01", "Jaipur Zone 1")),
        ("  Circle 1   (C-01)  ", NodeRef("C-01", "Circle 1")),
        ("Plain name", NodeRef(None, "Plain name")),
        (" (C-06)", NodeRef("C-06", None)),
        ("Circle 6 ()", NodeRef(None, "Circle 6")),
        ("Circle 6 ( )", NodeRef(None, "Circle 6")),
        ("   ", NodeRef(None, None)),
        ("", NodeRef(None, None)),
    ],
)
def test_parse_node(text: str, expected: NodeRef) -> None:
    assert mappers.parse_node(text) == expected


def test_node_from_obj() -> None:
    assert mappers.node_from_obj({"name": "A", "code": "C"}) == NodeRef("C", "A")
    assert mappers.node_from_obj({"name": " ", "code": ""}) == NodeRef(None, None)
    assert mappers.node_from_obj({"name": "A", "code": None}) == NodeRef(None, "A")


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Installed", InstallStatus.INSTALLED),
        (" faulty ", InstallStatus.FAULTY),
        ("DECOMMISSIONED", InstallStatus.DECOMMISSIONED),
    ],
)
def test_status(raw: str, expected: InstallStatus) -> None:
    assert mappers.to_install_status(raw) is expected


def test_phase_and_type() -> None:
    assert mappers.to_phase_type("Single") is PhaseType.SINGLE
    assert mappers.to_phase_type("three") is PhaseType.THREE
    assert mappers.to_install_type("Whole Current") is InstallType.WHOLE_CURRENT
    assert mappers.to_install_type("CT  Operated") is InstallType.CT_OPERATED
    assert mappers.to_install_type("ct operated") is InstallType.CT_OPERATED


def test_unknown_enum_warns(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        assert mappers.to_install_status("Exploded") is InstallStatus.UNKNOWN
    assert "install_status" in caplog.text
    assert "Exploded" in caplog.text
    assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 1
    assert mappers.to_phase_type(None) is PhaseType.UNKNOWN


def test_to_float() -> None:
    assert mappers.to_float("226", field="v") == 226.0
    assert mappers.to_float(3, field="v") == 3.0
    assert mappers.to_float(2.5, field="v") == 2.5
    assert mappers.to_optional_float("", field="v") is None
    assert mappers.to_optional_float(None, field="v") is None
    with pytest.raises(UpstreamProtocolError, match="v"):
        mappers.to_float("", field="v")
    with pytest.raises(UpstreamProtocolError):
        mappers.to_optional_float("abc", field="v")
    with pytest.raises(UpstreamProtocolError):
        mappers.to_float(True, field="v")
    with pytest.raises(UpstreamProtocolError):
        mappers.to_float("nan", field="v")


def test_timestamp() -> None:
    assert mappers.parse_timestamp("23/06/2026 23:30") == datetime(2026, 6, 23, 23, 30, tzinfo=IST)
    for bad in ("2026-06-23 23:30", "23/06/2026", "32/01/2026 00:00", 5):
        with pytest.raises(UpstreamProtocolError):
            mappers.parse_timestamp(bad)


def test_summary_meter() -> None:
    m = mappers.meter_from_summary(
        {
            "meterId": " J1 ",
            "serialNo": "L&84997 ",
            "make": " L&T",
            "phaseType": "three",
            "installStatus": "Faulty",
            "dtCode": "DT-009",
        }
    )
    assert (m.meter_id, m.serial_no, m.make) == ("J1", "L&84997", "L&T")
    assert m.phase_type is PhaseType.THREE
    assert m.install_status is InstallStatus.FAULTY
    assert m.dt_code == "DT-009"
    assert (m.install_type, m.build, m.hierarchy, m.geo) == (None, None, None, None)


def test_summary_missing_key() -> None:
    with pytest.raises(UpstreamProtocolError, match="serialNo"):
        mappers.meter_from_summary({"meterId": "J1"})


def test_export_meter_dt_fallback_and_geo() -> None:
    d = {
        "meterId": "J1",
        "serialNo": "S",
        "make": "HPL",
        "phaseType": "single",
        "installStatus": "Installed",
        "installType": "CT Operated",
        "build": "v2",
        "hierarchy": {
            k: {"name": f"n{k}", "code": f"c{k}"}
            for k in ("zone", "circle", "division", "subdivision", "substation", "feeder", "dt")
        },
        "geo": {"lat": 26.9, "lng": 75.8},
    }
    m = mappers.meter_from_export(d)
    assert m.dt_code == "cdt"
    assert m.geo == GeoPoint(26.9, 75.8)
    assert m.install_type is InstallType.CT_OPERATED
    assert m.build == "v2"
    assert m.hierarchy is not None
    assert mappers.meter_from_export({**d, "dtCode": "DT-1"}).dt_code == "DT-1"


def test_transformer_and_reading() -> None:
    t = mappers.transformer_from_dict(
        {"code": "DT-001", "name": "N", "feederCode": "F-001", "capacityKva": 100}
    )
    assert (t.code, t.feeder_code, t.capacity_kva) == ("DT-001", "F-001", 100)
    with pytest.raises(UpstreamProtocolError):
        mappers.transformer_from_dict({"code": "DT-001", "name": "N", "capacityKva": "x"})
    r = mappers.reading_from_dict(
        {"timestamp": "23/06/2026 00:00", "kwh": "1.5", "kvah": "2", "voltR": ""}
    )
    assert r.voltage_r is None
    assert r.kwh_register == 1.5
    assert r.at.tzinfo == IST


def test_geo() -> None:
    assert mappers.geo_from_strings("26.9", "75.8") == GeoPoint(26.9, 75.8)
    with pytest.raises(UpstreamProtocolError):
        mappers.geo_from_strings("999", "75.8")


def test_overflow_and_syntax() -> None:
    with pytest.raises(UpstreamProtocolError):
        mappers.to_float(10**400, field="v")
    with pytest.raises(UpstreamProtocolError):
        mappers.to_float("1_0", field="v")
    with pytest.raises(UpstreamProtocolError, match="capacityKva"):
        mappers.transformer_from_dict({"code": "a", "name": "b", "capacityKva": 100.7})
    assert (
        mappers.transformer_from_dict({"code": "a", "name": "b", "capacityKva": "100"}).capacity_kva
        == 100
    )
