from app.services.quality.checks.geo_checks import MissingGeo
from app.services.quality.models import Severity
from tests.support.hierarchy_factory import make_meter, quality_context


def test_flags_meters_without_a_position() -> None:
    (issue,) = MissingGeo().run(quality_context([make_meter("J1"), make_meter("J2", geo=None)]))
    assert (issue.check, issue.severity, issue.entity, issue.entity_id) == (
        "missing_geo",
        Severity.WARNING,
        "meter",
        "J2",
    )
    assert issue.evidence == {}


def test_all_positioned_raises_nothing() -> None:
    assert MissingGeo().run(quality_context([make_meter("J1")])) == []
