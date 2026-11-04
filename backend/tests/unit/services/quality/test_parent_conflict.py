from app.services.quality.checks.hierarchy_checks import ParentConflictCheck
from app.services.quality.models import Severity
from tests.support.hierarchy_factory import make_meter, quality_context

FEEDER = "Z-01/C-01/D-01/SD-01/SS-01/F-001"


def test_flags_a_dt_code_under_two_parents() -> None:
    meters = [make_meter("J1"), make_meter("J2", feeder=("F-002", "Feeder 2"))]
    (issue,) = ParentConflictCheck().run(quality_context(meters))
    assert (issue.check, issue.severity, issue.entity, issue.entity_id) == (
        "parent_conflict",
        Severity.ERROR,
        "transformer",
        "DT-001",
    )
    assert issue.evidence == {
        "paths": [FEEDER, FEEDER.replace("F-001", "F-002")],
        "meter_ids": ["J1", "J2"],
    }


def test_unique_dt_parents_raise_nothing() -> None:
    meters = [make_meter("J1"), make_meter("J2", dt=("DT-002", "Two"))]
    assert ParentConflictCheck().run(quality_context(meters)) == []
