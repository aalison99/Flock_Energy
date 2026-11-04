from app.services.quality.checks.dt_checks import DtCodeMismatch
from app.services.quality.models import Severity
from tests.support.hierarchy_factory import make_meter, quality_context


def test_flags_meter_dt_code_that_differs_from_its_path() -> None:
    meters = [make_meter("J1"), make_meter("J2", dt_code="DT-002")]
    (issue,) = DtCodeMismatch().run(quality_context(meters))
    assert (issue.check, issue.severity, issue.entity, issue.entity_id) == (
        "dt_code_mismatch",
        Severity.WARNING,
        "meter",
        "J2",
    )
    assert issue.evidence == {"dt_code": "DT-002", "hierarchy_dt_code": "DT-001"}


def test_repaired_dt_code_is_compared_and_unplaced_meters_are_skipped() -> None:
    meters = [
        make_meter("J0"),
        make_meter("J1", dt=(None, "Some DT 1"), dt_code="DT-001"),  # repaired to DT-001 from J0
        make_meter(
            "J2", dt=(None, None), dt_code="DT-001"
        ),  # unplaced: reported by unplaced_meter instead
    ]
    assert DtCodeMismatch().run(quality_context(meters)) == []


def test_missing_dt_code_counts_as_a_mismatch() -> None:
    (issue,) = DtCodeMismatch().run(quality_context([make_meter("J1", dt_code=None)]))
    assert issue.evidence == {"dt_code": None, "hierarchy_dt_code": "DT-001"}


def test_agreeing_codes_and_meters_without_a_path_raise_nothing() -> None:
    meters = [make_meter("J1"), make_meter("J2", hierarchy=False)]
    assert DtCodeMismatch().run(quality_context(meters)) == []
