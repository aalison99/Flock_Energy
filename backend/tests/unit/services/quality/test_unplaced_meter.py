from app.services.quality.checks.hierarchy_checks import UnplacedMeter
from app.services.quality.models import Severity
from tests.support.hierarchy_factory import make_meter, quality_context


def test_flags_meters_the_builder_could_not_place() -> None:
    meters = [make_meter("J1"), make_meter("J2", division=(None, None))]
    (issue,) = UnplacedMeter().run(quality_context(meters))
    assert (issue.check, issue.severity, issue.entity, issue.entity_id) == (
        "unplaced_meter",
        Severity.WARNING,
        "meter",
        "J2",
    )
    assert issue.evidence == {"placed_under": "Z-01/C-01"}


def test_meter_with_no_zone_is_placed_under_nothing() -> None:
    (issue,) = UnplacedMeter().run(quality_context([make_meter("J1", zone=(None, None))]))
    assert issue.evidence == {"placed_under": None}


def test_fully_placed_meters_raise_nothing() -> None:
    assert UnplacedMeter().run(quality_context([make_meter("J1")])) == []
