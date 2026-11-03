"""Detail sub-registry: two built-in formats, unknown shapes, one-class extension."""

import pytest

from app.domain.exceptions import UpstreamProtocolError
from app.portal.parsers.detail_formats import DetailFormatRegistry, default_detail_formats
from app.portal.parsers.detail_formats.legacy import LegacyFormat
from app.portal.parsers.detail_formats.v2 import V2Format

CANON = {
    "meter_id": "J1",
    "serial_no": "S1",
    "make": "HPL",
    "phase_type": "single",
    "install_status": "Installed",
    "install_type": "Whole Current",
}
LEGACY = {
    "data": [
        {"parameterName": "Meter ID", "parameterValue": "J1"},
        {"parameterName": "Serial No", "parameterValue": "S1"},
        {"parameterName": "Make", "parameterValue": "HPL"},
        {"parameterName": "Phase Type", "parameterValue": "single"},
        {"parameterName": "Installation Status", "parameterValue": "Installed"},
        {"parameterName": "Installation Type", "parameterValue": "Whole Current"},
    ]
}
V2 = {
    "classData": '{"installed_meter":{"MeterId":"J1","SerialNo":"S1","Make":"HPL",'
    '"PhaseType":"single","InstallationStatus":"Installed","InstallationType":"Whole Current"}}'
}


def test_legacy() -> None:
    fmt, fields = default_detail_formats().resolve(LEGACY)
    assert isinstance(fmt, LegacyFormat) and fmt.build == "legacy"
    assert fields == CANON


def test_v2() -> None:
    fmt, fields = default_detail_formats().resolve(V2)
    assert isinstance(fmt, V2Format) and fmt.build == "v2"
    assert fields == CANON


def test_unknown_shape() -> None:
    with pytest.raises(UpstreamProtocolError, match=r"unknown detail format, keys=\['zzz'\]"):
        default_detail_formats().resolve({"zzz": 1})


def test_missing_label_and_bad_class_data() -> None:
    with pytest.raises(UpstreamProtocolError):
        default_detail_formats().resolve({"data": []})
    with pytest.raises(UpstreamProtocolError):
        default_detail_formats().resolve({"classData": "{nope"})
    with pytest.raises(UpstreamProtocolError):
        default_detail_formats().resolve({"classData": '{"installed_meter": {}}'})


def test_third_format_is_one_class_and_one_register() -> None:
    class V3Format:
        build = "v3"

        def matches(self, detail: dict[str, object]) -> bool:
            return "v3" in detail

        def fields(self, detail: dict[str, object]) -> dict[str, str]:
            return CANON

    reg = DetailFormatRegistry()
    reg.register(V3Format())
    fmt, fields = reg.resolve({"v3": True})
    assert fmt.build == "v3" and fields == CANON
