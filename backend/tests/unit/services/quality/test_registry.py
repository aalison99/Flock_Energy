from app.services.quality.registry import CHECKS

EXPECTED = {
    "name_conflict": "warning",
    "blank_field_repaired": "info",
    "unplaced_meter": "warning",
    "parent_conflict": "error",
    "dt_code_mismatch": "warning",
    "unknown_dt": "warning",
    "dt_without_meters": "info",
    "dt_feeder_mismatch": "warning",
    "missing_geo": "warning",
    "geo_outlier": "warning",
}


def test_registry_lists_every_check_once_with_its_severity() -> None:
    assert {c.id: c.severity.value for c in CHECKS} == EXPECTED
    assert len(CHECKS) == len(EXPECTED)


def test_every_check_has_a_description_and_serial_make_check_is_dropped() -> None:
    assert all(c.description for c in CHECKS)
    assert "serial_make_mismatch" not in {c.id for c in CHECKS}
