from app.domain.models import HierarchyLevel, InstallStatus
from app.services.hierarchy.builder import (
    AltName,
    ParentConflict,
    Repair,
    build_hierarchy,
    subtree_meter_ids,
)
from tests.support.hierarchy_factory import (
    assert_children_sum_to_parent,
    make_meter,
    make_transformer,
)

DT = "Z-01/C-01/D-01/SD-01/SS-01/F-001/DT-001"
FEEDER = "Z-01/C-01/D-01/SD-01/SS-01/F-001"


def test_node_ids_are_full_code_paths_and_the_tree_links_up() -> None:
    snap = build_hierarchy([make_meter("J1")], [])
    assert snap.roots == ("Z-01",)
    node = snap.nodes[DT]
    assert (node.level, node.code, node.parent_id) == (HierarchyLevel.DT, "DT-001", FEEDER)
    assert snap.nodes[FEEDER].child_ids == (DT,)
    assert snap.nodes["Z-01"].parent_id is None
    assert node.meter_ids == ("J1",)
    assert len(snap.nodes) == 7


def test_same_code_under_different_parents_stays_separate_nodes() -> None:
    meters = [
        make_meter("J1"),
        make_meter("J2", circle=("C-02", "Circle 2")),
        make_meter("J3", circle=("C-03", "Circle 3")),
    ]
    snap = build_hierarchy(meters, [])
    division_ids = [n.id for n in snap.nodes.values() if n.level is HierarchyLevel.DIVISION]
    assert sorted(division_ids) == [
        "Z-01/C-01/D-01",
        "Z-01/C-02/D-01",
        "Z-01/C-03/D-01",
    ]


def test_children_sorted_by_code_and_roots_sorted() -> None:
    meters = [
        make_meter("J1", zone=("Z-02", "Jaipur Zone 2"), circle=("C-09", "Circle 9")),
        make_meter("J2", circle=("C-03", "Circle 3")),
        make_meter("J3", circle=("C-01", "Circle 1")),
    ]
    snap = build_hierarchy(meters, [])
    assert snap.roots == ("Z-01", "Z-02")
    assert snap.nodes["Z-01"].child_ids == ("Z-01/C-01", "Z-01/C-03")


def test_deterministic_regardless_of_input_order() -> None:
    meters = [
        make_meter("J3", circle=("C-02", "Circle 2")),
        make_meter("J1"),
        make_meter("J2", circle=(None, "Circle 2")),
    ]
    forward = build_hierarchy(meters, [make_transformer()])
    backward = build_hierarchy(list(reversed(meters)), [make_transformer()])
    assert forward == backward


def test_most_frequent_name_is_canonical_others_become_alt_names() -> None:
    meters = [
        make_meter("J1", feeder=("F-001", "Feeder 1")),
        make_meter("J2", feeder=("F-001", "Feeder 1")),
        make_meter("J3", feeder=("F-001", "Old Feeder")),
        make_meter("J4", feeder=("F-001", "Feeder One")),
    ]
    node = build_hierarchy(meters, []).nodes[FEEDER]
    assert node.name == "Feeder 1"
    assert node.alt_names == (
        AltName("Feeder One", ("J4",)),
        AltName("Old Feeder", ("J3",)),
    )


def test_name_tie_goes_to_the_alphabetically_first() -> None:
    meters = [
        make_meter("J1", feeder=("F-001", "Zeta Feeder")),
        make_meter("J2", feeder=("F-001", "Alpha Feeder")),
    ]
    node = build_hierarchy(meters, []).nodes[FEEDER]
    assert node.name == "Alpha Feeder"
    assert node.alt_names == (AltName("Zeta Feeder", ("J1",)),)


def test_dt_list_name_wins_even_against_the_majority() -> None:
    meters = [
        make_meter("J1", dt=("DT-001", "Old Xfmr")),
        make_meter("J2", dt=("DT-001", "Old Xfmr")),
        make_meter("J3", dt=("DT-001", "Listed DT")),
    ]
    node = build_hierarchy(meters, [make_transformer(name="Listed DT")]).nodes[DT]
    assert node.name == "Listed DT"
    assert node.alt_names == (AltName("Old Xfmr", ("J1", "J2")),)


def test_dt_not_in_list_uses_most_frequent_name() -> None:
    meters = [
        make_meter("J1", dt=("DT-001", "A")),
        make_meter("J2", dt=("DT-001", "B")),
        make_meter("J3", dt=("DT-001", "B")),
    ]
    assert build_hierarchy(meters, []).nodes[DT].name == "B"


def test_blank_code_repaired_from_sibling_meters_with_the_same_name() -> None:
    meters = [
        make_meter("J1", circle=("C-07", "Circle 1")),  # name does not follow the rule
        make_meter("J2", circle=(None, "Circle 1")),
    ]
    snap = build_hierarchy(meters, [])
    assert snap.repairs == (Repair("J2", HierarchyLevel.CIRCLE, "code", None, "C-07", "sibling"),)
    assert "Z-01/C-07" in snap.nodes
    assert (
        snap.nodes["Z-01/C-07"].meter_ids == () and len(subtree_meter_ids(snap, "Z-01/C-07")) == 2
    )


def test_sibling_code_most_common_then_smallest_on_tie() -> None:
    meters = [
        make_meter("J1", circle=("C-09", "Odd")),
        make_meter("J2", circle=("C-05", "Odd")),
        make_meter("J3", circle=("C-09", "Odd")),
        make_meter("J4", circle=(None, "Odd")),
    ]
    assert build_hierarchy(meters, []).repairs[0].after == "C-09"
    tie = [meters[0], meters[1], meters[3]]
    assert build_hierarchy(tie, []).repairs[0].after == "C-05"


def test_sibling_must_share_the_parent_path() -> None:
    meters = [
        make_meter("J1", division=("D-09", "Division 5"), circle=("C-02", "Circle 2")),
        make_meter("J2", division=(None, "Division 5")),  # under C-01: J1 is not a sibling
    ]
    repair = build_hierarchy(meters, []).repairs[0]
    assert (repair.after, repair.method) == ("D-05", "number_rule")


def test_blank_code_falls_back_to_the_number_rule() -> None:
    snap = build_hierarchy([make_meter("J1", circle=(None, "Circle 6"))], [])
    assert snap.repairs == (
        Repair("J1", HierarchyLevel.CIRCLE, "code", None, "C-06", "number_rule"),
    )
    assert "Z-01/C-06" in snap.nodes


def test_blank_name_repaired_from_the_nodes_canonical_name() -> None:
    meters = [
        make_meter("J1", substation=("SS-01", "Grid One")),
        make_meter("J2", substation=("SS-01", None)),
    ]
    snap = build_hierarchy(meters, [])
    assert snap.repairs == (
        Repair("J2", HierarchyLevel.SUBSTATION, "name", None, "Grid One", "sibling"),
    )
    assert snap.nodes[FEEDER.rsplit("/", 1)[0]].name == "Grid One"
    assert snap.nodes[FEEDER.rsplit("/", 1)[0]].alt_names == ()


def test_blank_name_falls_back_to_the_number_rule() -> None:
    snap = build_hierarchy([make_meter("J1", feeder=("F-005", None))], [])
    assert snap.repairs == (
        Repair("J1", HierarchyLevel.FEEDER, "name", None, "Feeder 5", "number_rule"),
    )


def test_dt_blank_name_uses_the_dt_list() -> None:
    snap = build_hierarchy(
        [make_meter("J1", dt=("DT-001", None))], [make_transformer(name="Listed DT")]
    )
    assert snap.nodes[DT].name == "Listed DT"
    assert snap.repairs[0].after == "Listed DT"
    assert snap.repairs[0].method == "dt_list"


def test_padded_names_and_codes_are_trimmed_not_aliased() -> None:
    meters = [
        make_meter("J1"),
        make_meter("J2", feeder=(" F-001 ", " Feeder 1 ")),
        make_meter("J3", circle=("C-01", "Circle 1 ")),
    ]
    snap = build_hierarchy(meters, [])
    assert all(n.alt_names == () for n in snap.nodes.values())
    assert sum(1 for n in snap.nodes.values() if n.level is HierarchyLevel.FEEDER) == 1


def test_unplaced_count_is_per_node_and_meter_count_balances() -> None:
    meters = [make_meter("J1"), make_meter("J2", division=(None, None))]
    snap = build_hierarchy(meters, [])
    assert snap.nodes["Z-01/C-01"].unplaced_count == 1
    assert snap.nodes[DT].unplaced_count == 0
    assert_children_sum_to_parent(snap, meters)


def test_both_blank_is_unplaced_under_the_deepest_complete_ancestor() -> None:
    meters = [make_meter("J1"), make_meter("J2", division=(None, None))]
    snap = build_hierarchy(meters, [])
    assert snap.unplaced == ("J2",)
    assert snap.repairs == ()
    assert snap.nodes["Z-01/C-01"].meter_ids == ("J2",)
    assert subtree_meter_ids(snap, "Z-01/C-01") == ["J1", "J2"]
    assert subtree_meter_ids(snap, DT) == ["J1"]


def test_unrepairable_single_blank_is_unplaced_too() -> None:
    snap = build_hierarchy([make_meter("J1", circle=(None, "Weird name"))], [])
    assert snap.unplaced == ("J1",)
    assert snap.repairs == ()
    assert snap.nodes["Z-01"].meter_ids == ("J1",)


def test_blank_zone_leaves_the_meter_in_no_node() -> None:
    snap = build_hierarchy([make_meter("J1", zone=(None, None))], [])
    assert snap.unplaced == ("J1",)
    assert snap.nodes == {} and snap.roots == ()


def test_meters_without_hierarchy_are_listed_not_placed() -> None:
    snap = build_hierarchy([make_meter("J1"), make_meter("J2", hierarchy=False)], [])
    assert snap.meters_without_hierarchy == ("J2",)
    assert snap.unplaced == ()
    assert subtree_meter_ids(snap, "Z-01") == ["J1"]


def test_repaired_meter_continues_down_the_path() -> None:
    snap = build_hierarchy([make_meter("J1", circle=(None, "Circle 4"))], [])
    assert snap.nodes["Z-01/C-04/D-01/SD-01/SS-01/F-001/DT-001"].meter_ids == ("J1",)


def test_dt_under_two_parents_is_placed_twice_and_reported() -> None:
    meters = [
        make_meter("J1"),
        make_meter("J2", feeder=("F-002", "Feeder 2")),
        make_meter("J3", feeder=("F-002", "Feeder 2")),
    ]
    snap = build_hierarchy(meters, [])
    assert snap.conflicts == (
        ParentConflict(
            "DT-001",
            [FEEDER, FEEDER.replace("F-001", "F-002")],
            ("J1", "J2", "J3"),
        ),
    )
    assert snap.nodes[DT].meter_ids == ("J1",)
    assert snap.nodes[DT.replace("F-001", "F-002")].meter_ids == ("J2", "J3")


def test_no_conflict_when_other_levels_repeat_codes_under_different_parents() -> None:
    meters = [make_meter("J1"), make_meter("J2", circle=("C-02", "Circle 2"), dt=("DT-002", "X"))]
    assert build_hierarchy(meters, []).conflicts == ()


def test_status_counts_roll_up_and_children_sum_to_the_parent() -> None:
    meters = [
        make_meter("J1", status=InstallStatus.INSTALLED),
        make_meter("J2", status=InstallStatus.FAULTY),
        make_meter("J3", status=InstallStatus.FAULTY, circle=("C-02", "Circle 2")),
        make_meter("J4", status=InstallStatus.DECOMMISSIONED, dt=("DT-002", "Two")),
        make_meter("J5", division=(None, None)),
    ]
    snap = build_hierarchy(meters, [])
    assert snap.nodes["Z-01"].status_counts == {"installed": 2, "faulty": 2, "decommissioned": 1}
    assert_children_sum_to_parent(snap, meters)
