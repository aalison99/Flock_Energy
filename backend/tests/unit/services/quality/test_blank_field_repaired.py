from app.services.quality.checks.hierarchy_checks import BlankFieldRepaired
from app.services.quality.models import Severity
from tests.support.hierarchy_factory import make_meter, quality_context


def test_one_info_issue_per_repair_with_before_after_method() -> None:
    meters = [make_meter("J1", circle=(None, "Circle 6")), make_meter("J2", feeder=("F-001", None))]
    issues = BlankFieldRepaired().run(quality_context(meters))
    assert [(i.entity, i.entity_id, i.severity) for i in issues] == [
        ("meter", "J1", Severity.INFO),
        ("meter", "J2", Severity.INFO),
    ]
    assert issues[0].evidence == {
        "level": "circle",
        "field": "code",
        "before": None,
        "after": "C-06",
        "method": "number_rule",
    }
    assert issues[1].evidence["after"] == "Feeder 1"


def test_nothing_repaired_nothing_reported() -> None:
    assert BlankFieldRepaired().run(quality_context([make_meter("J1")])) == []
