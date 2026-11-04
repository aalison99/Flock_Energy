"""Small synthetic meters and transformers for hierarchy and quality tests."""

from collections import Counter

from app.domain.models import (
    GeoPoint,
    HierarchyLevel,
    HierarchyPath,
    InstallStatus,
    InstallType,
    Meter,
    NodeRef,
    PhaseType,
    Transformer,
)
from app.services.hierarchy.builder import HierarchySnapshot, build_hierarchy
from app.services.quality.models import QualityContext

Ref = tuple[str | None, str | None]

DEFAULT_PATH: dict[str, Ref] = {
    "zone": ("Z-01", "Jaipur Zone 1"),
    "circle": ("C-01", "Circle 1"),
    "division": ("D-01", "Division 1"),
    "subdivision": ("SD-01", "Subdivision 1"),
    "substation": ("SS-01", "Substation 1"),
    "feeder": ("F-001", "Feeder 1"),
    "dt": ("DT-001", "Some DT 1"),
}

DEFAULT_GEO = GeoPoint(26.9, 75.8)


def make_meter(
    meter_id: str,
    *,
    status: InstallStatus = InstallStatus.INSTALLED,
    dt_code: str | None = "default",
    geo: GeoPoint | None = DEFAULT_GEO,
    hierarchy: bool = True,
    **levels: Ref,
) -> Meter:
    """A meter on the default path; keyword `circle=("C-02", "Circle 2")` etc. override levels.

    `dt_code="default"` means "same as the path's DT code".
    """
    path = {**DEFAULT_PATH, **levels}
    refs = {level: NodeRef(code=code, name=name) for level, (code, name) in path.items()}
    return Meter(
        meter_id=meter_id,
        serial_no=f"SN{meter_id}",
        make="HPL",
        phase_type=PhaseType.SINGLE,
        install_status=status,
        install_type=InstallType.WHOLE_CURRENT,
        build="v2",
        dt_code=path["dt"][0] if dt_code == "default" else dt_code,
        hierarchy=HierarchyPath(**refs) if hierarchy else None,
        geo=geo,
    )


def make_transformer(
    code: str = "DT-001", name: str = "Some DT 1", feeder_code: str | None = "F-001"
) -> Transformer:
    return Transformer(code=code, name=name, feeder_code=feeder_code, capacity_kva=100)


def assert_children_sum_to_parent(snap: HierarchySnapshot, meters: list[Meter]) -> None:
    """meter_count = sum of children's meter_count + unplaced_count, for every node;
    and unplaced_count matches the unplaced meters attached to non-DT nodes."""
    status = {m.meter_id: m.install_status.value for m in meters}
    for node in snap.nodes.values():
        expected = Counter()
        for child_id in node.child_ids:
            expected.update(snap.nodes[child_id].status_counts)
        if node.level is HierarchyLevel.DT:
            expected.update(status[i] for i in node.meter_ids)
            assert node.unplaced_count == 0, node.id
        else:
            assert node.unplaced_count == len(node.meter_ids), node.id
            expected.update(status[i] for i in node.meter_ids)
        assert sum(node.status_counts.values()) == sum(
            snap.nodes[c].meter_count for c in node.child_ids
        ) + node.unplaced_count + (len(node.meter_ids) if node.level is HierarchyLevel.DT else 0)
        assert dict(expected) == dict(node.status_counts), node.id


def quality_context(
    meters: list[Meter], transformers: list[Transformer] | None = None
) -> QualityContext:
    """A QualityContext whose snapshot is built from the same inputs."""
    transformers = transformers if transformers is not None else []
    return QualityContext(meters, transformers, build_hierarchy(meters, transformers))
