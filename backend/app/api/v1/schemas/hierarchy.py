"""Network hierarchy response schemas and the mappings from service results."""

from pydantic import BaseModel, ConfigDict, Field

from app.domain.models import HierarchyLevel
from app.services.results import AliasView, NodeDetail, NodeSummary, TreeNode

_ID_DESCRIPTION = (
    "Node id: the codes from zone down to the node joined by '/', "
    "e.g. Z-01/C-01/D-07/SD-07/SS-07/F-007/DT-007."
)


class StatusBreakdown(BaseModel):
    """Meters per installation status."""

    installed: int = Field(description="Meters with status installed.")
    faulty: int = Field(description="Meters with status faulty.")
    decommissioned: int = Field(description="Meters with status decommissioned.")
    unknown: int = Field(description="Meters whose status is unknown.")


class TreeNodeOut(BaseModel):
    """A hierarchy node, its subtree totals and its children (down to the requested depth)."""

    id: str = Field(description=_ID_DESCRIPTION)
    level: HierarchyLevel = Field(description="Hierarchy level.")
    code: str = Field(description="Node code, e.g. D-07.")
    name: str = Field(description="Canonical node name.")
    meter_count: int = Field(description="Meters in this node's whole subtree.")
    status_breakdown: StatusBreakdown = Field(description="Subtree meters per status.")
    unplaced_count: int = Field(
        description="Meters attached here because a lower level was unfixable."
    )
    children: list["TreeNodeOut"] = Field(
        description="Child nodes sorted by code; empty at the depth limit and at DTs."
    )


class TreeResponse(BaseModel):
    """The hierarchy tree: one entry per zone."""

    items: list[TreeNodeOut] = Field(description="Zones, sorted by code.")


class NodeSummaryOut(BaseModel):
    """A node without children: a step on the path or a child in a listing."""

    id: str = Field(description=_ID_DESCRIPTION)
    level: HierarchyLevel = Field(description="Hierarchy level.")
    code: str = Field(description="Node code.")
    name: str = Field(description="Canonical node name.")
    meter_count: int = Field(description="Meters in the node's whole subtree.")


class AltNameOut(BaseModel):
    """A non-canonical name seen for the node."""

    name: str = Field(description="The alternative name.")
    meter_ids: list[str] = Field(description="Meters that used this name.")


class NodeDetailOut(BaseModel):
    """One node with its path from the zone, children, counts and alias names."""

    id: str = Field(description=_ID_DESCRIPTION)
    level: HierarchyLevel = Field(description="Hierarchy level.")
    code: str = Field(description="Node code.")
    name: str = Field(description="Canonical node name.")
    path: list[NodeSummaryOut] = Field(description="Zone down to this node, inclusive.")
    children: list[NodeSummaryOut] = Field(description="Child nodes sorted by code.")
    meter_count: int = Field(description="Meters in this node's whole subtree.")
    status_breakdown: StatusBreakdown = Field(description="Subtree meters per status.")
    unplaced_count: int = Field(
        description="Meters attached here because a lower level was unfixable."
    )
    alt_names: list[AltNameOut] = Field(description="Other names used for this node.")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "Z-01/C-01/D-07/SD-07/SS-07/F-007/DT-007",
                "level": "dt",
                "code": "DT-007",
                "name": "Sanganer DT 7",
                "path": [
                    {
                        "id": "Z-01",
                        "level": "zone",
                        "code": "Z-01",
                        "name": "Jaipur Zone 1",
                        "meter_count": 120,
                    }
                ],
                "children": [],
                "meter_count": 13,
                "status_breakdown": {
                    "installed": 7,
                    "faulty": 4,
                    "decommissioned": 2,
                    "unknown": 0,
                },
                "unplaced_count": 0,
                "alt_names": [
                    {"name": "Old Malviya Nagar Xfmr", "meter_ids": ["J100400", "J100401"]}
                ],
            }
        }
    )


def _breakdown(counts: dict[str, int]) -> StatusBreakdown:
    return StatusBreakdown(**counts)


def to_tree_node_out(node: TreeNode) -> TreeNodeOut:
    return TreeNodeOut(
        id=node.id,
        level=node.level,
        code=node.code,
        name=node.name,
        meter_count=node.meter_count,
        status_breakdown=_breakdown(node.status_breakdown),
        unplaced_count=node.unplaced_count,
        children=[to_tree_node_out(c) for c in node.children],
    )


def _summary(node: NodeSummary) -> NodeSummaryOut:
    return NodeSummaryOut(
        id=node.id,
        level=node.level,
        code=node.code,
        name=node.name,
        meter_count=node.meter_count,
    )


def _alias(alias: AliasView) -> AltNameOut:
    return AltNameOut(name=alias.name, meter_ids=list(alias.meter_ids))


def to_node_detail_out(node: NodeDetail) -> NodeDetailOut:
    return NodeDetailOut(
        id=node.id,
        level=node.level,
        code=node.code,
        name=node.name,
        path=[_summary(p) for p in node.path],
        children=[_summary(c) for c in node.children],
        meter_count=node.meter_count,
        status_breakdown=_breakdown(node.status_breakdown),
        unplaced_count=node.unplaced_count,
        alt_names=[_alias(a) for a in node.alt_names],
    )
