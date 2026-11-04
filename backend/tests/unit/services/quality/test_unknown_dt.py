from app.services.quality.checks.dt_checks import UnknownDt
from app.services.quality.models import Severity
from tests.support.hierarchy_factory import make_meter, make_transformer, quality_context


def test_flags_meter_dt_codes_missing_from_the_dt_list() -> None:
    meters = [make_meter("J1"), make_meter("J2", dt=("DT-099", "Ghost"))]
    (issue,) = UnknownDt().run(quality_context(meters, [make_transformer()]))
    assert (issue.check, issue.severity, issue.entity, issue.entity_id) == (
        "unknown_dt",
        Severity.WARNING,
        "meter",
        "J2",
    )
    assert issue.evidence == {"dt_code": "DT-099"}


def test_listed_or_absent_dt_codes_raise_nothing() -> None:
    meters = [make_meter("J1"), make_meter("J2", dt_code=None)]
    assert UnknownDt().run(quality_context(meters, [make_transformer()])) == []
