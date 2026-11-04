from app.services.quality.checks.dt_checks import DtWithoutMeters
from app.services.quality.models import Severity
from tests.support.hierarchy_factory import make_meter, make_transformer, quality_context


def test_flags_listed_dts_nobody_uses() -> None:
    transformers = [make_transformer(), make_transformer("DT-002", "Idle")]
    (issue,) = DtWithoutMeters().run(quality_context([make_meter("J1")], transformers))
    assert (issue.check, issue.severity, issue.entity, issue.entity_id) == (
        "dt_without_meters",
        Severity.INFO,
        "transformer",
        "DT-002",
    )
    assert issue.evidence == {"name": "Idle"}


def test_dt_used_only_by_a_meters_own_dt_code_is_not_idle() -> None:
    meters = [make_meter("J1", dt_code="DT-002")]
    transformers = [make_transformer("DT-002", "Used")]
    assert DtWithoutMeters().run(quality_context(meters, transformers)) == []
