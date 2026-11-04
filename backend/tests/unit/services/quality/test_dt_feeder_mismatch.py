from app.services.quality.checks.dt_checks import DtFeederMismatch
from app.services.quality.models import Severity
from tests.support.hierarchy_factory import make_meter, make_transformer, quality_context


def test_flags_a_list_feeder_that_the_meters_paths_contradict() -> None:
    transformers = [make_transformer(feeder_code="F-009")]
    (issue,) = DtFeederMismatch().run(quality_context([make_meter("J1")], transformers))
    assert (issue.check, issue.severity, issue.entity, issue.entity_id) == (
        "dt_feeder_mismatch",
        Severity.WARNING,
        "transformer",
        "DT-001",
    )
    assert issue.evidence == {"list_feeder_code": "F-009", "path_feeder_codes": ["F-001"]}


def test_matching_feeder_unset_feeder_and_unused_dt_raise_nothing() -> None:
    transformers = [
        make_transformer(),
        make_transformer("DT-002", "No feeder", feeder_code=None),
        make_transformer("DT-003", "Unused", feeder_code="F-009"),
    ]
    meters = [make_meter("J1"), make_meter("J2", dt=("DT-002", "No feeder"))]
    assert DtFeederMismatch().run(quality_context(meters, transformers)) == []
