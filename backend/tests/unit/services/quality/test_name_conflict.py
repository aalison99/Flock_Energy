from app.services.quality.checks.hierarchy_checks import NameConflict
from app.services.quality.models import Severity
from tests.support.hierarchy_factory import make_meter, make_transformer, quality_context

DT = "Z-01/C-01/D-01/SD-01/SS-01/F-001/DT-001"


def test_flags_a_dt_with_an_alias_and_names_the_dt_list_as_source() -> None:
    meters = [
        make_meter("J1", dt=("DT-001", "Listed DT")),
        make_meter("J2", dt=("DT-001", "Old Name")),
        make_meter("J3", dt=("DT-001", "Old Name")),
    ]
    ctx = quality_context(meters, [make_transformer(name="Listed DT")])
    (issue,) = NameConflict().run(ctx)
    assert (issue.check, issue.severity, issue.entity, issue.entity_id) == (
        "name_conflict",
        Severity.WARNING,
        "node",
        DT,
    )
    assert issue.evidence == {
        "canonical": "Listed DT",
        "canonical_source": "dt_list",
        "aliases": [{"name": "Old Name", "meter_ids": ["J2", "J3"]}],
    }


def test_non_dt_nodes_use_the_most_common_name_as_source() -> None:
    meters = [make_meter("J1"), make_meter("J2"), make_meter("J3", feeder=("F-001", "Odd"))]
    (issue,) = NameConflict().run(quality_context(meters))
    assert issue.evidence["canonical_source"] == "most_common_name"
    assert issue.evidence["canonical"] == "Feeder 1"


def test_consistent_names_raise_nothing() -> None:
    assert NameConflict().run(quality_context([make_meter("J1"), make_meter("J2")])) == []
