"""Network hierarchy use cases over the indexed meters (the tree is rebuilt per request)."""

from app.domain.exceptions import IndexNotReadyError, NotFoundError
from app.domain.models import InstallStatus, Meter, PageResult
from app.repositories.interfaces import MeterRepository, TransformerRepository
from app.services.hierarchy.builder import (
    HierarchySnapshot,
    Node,
    build_hierarchy,
    subtree_meter_ids,
)
from app.services.results import AliasView, NodeDetail, NodeSummary, TreeNode

_STATUSES = tuple(s.value for s in InstallStatus)


def _breakdown(node: Node) -> dict[str, int]:
    """Every status key, zero-filled, so clients can rely on the shape."""
    return {status: node.status_counts.get(status, 0) for status in _STATUSES}


def _meter_count(node: Node) -> int:
    return sum(node.status_counts.values())


def _summary(node: Node) -> NodeSummary:
    return NodeSummary(node.id, node.level, node.code, node.name, _meter_count(node))


class HierarchyService:
    def __init__(self, meters: MeterRepository, transformers: TransformerRepository) -> None:
        self._meters = meters
        self._transformers = transformers

    async def _load(self) -> tuple[HierarchySnapshot, list[Meter]]:
        meters = await self._meters.list_all()
        if not meters:
            raise IndexNotReadyError("the local index is empty; a sync is needed")
        snapshot = build_hierarchy(meters, await self._transformers.list_all())
        return snapshot, meters

    @staticmethod
    def _find(snapshot: HierarchySnapshot, node_id: str) -> Node:
        node = snapshot.nodes.get(node_id)
        if node is None:
            raise NotFoundError(f"hierarchy node {node_id} not found")
        return node

    async def tree(self, depth: int) -> list[TreeNode]:
        """The tree down to `depth` levels (1 = zones only)."""
        snapshot, _ = await self._load()

        def build(node_id: str, remaining: int) -> TreeNode:
            node = snapshot.nodes[node_id]
            kids = [build(c, remaining - 1) for c in node.child_ids] if remaining > 1 else []
            return TreeNode(
                node.id,
                node.level,
                node.code,
                node.name,
                _meter_count(node),
                _breakdown(node),
                node.unplaced_count,
                kids,
            )

        return [build(root, depth) for root in snapshot.roots]

    async def node(self, node_id: str) -> NodeDetail:
        snapshot, _ = await self._load()
        node = self._find(snapshot, node_id)
        chain: list[Node] = []
        cursor: Node | None = node
        while cursor is not None:
            chain.append(cursor)
            cursor = snapshot.nodes[cursor.parent_id] if cursor.parent_id else None
        return NodeDetail(
            id=node.id,
            level=node.level,
            code=node.code,
            name=node.name,
            path=[_summary(n) for n in reversed(chain)],
            children=[_summary(snapshot.nodes[c]) for c in node.child_ids],
            meter_count=_meter_count(node),
            status_breakdown=_breakdown(node),
            unplaced_count=node.unplaced_count,
            alt_names=[AliasView(a.name, a.meter_ids) for a in node.alt_names],
        )

    async def meters_under(self, node_id: str, page: int, page_size: int) -> PageResult[Meter]:
        """Meters in the node's subtree, ordered by meter id."""
        snapshot, meters = await self._load()
        self._find(snapshot, node_id)
        ids = subtree_meter_ids(snapshot, node_id)
        by_id = {m.meter_id: m for m in meters}
        start = (page - 1) * page_size
        return PageResult(items=[by_id[i] for i in ids[start : start + page_size]], total=len(ids))
