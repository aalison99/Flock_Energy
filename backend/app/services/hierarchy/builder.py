"""Rebuild the network tree from meters: pure, deterministic, no I/O.

The tree is rebuilt in memory on every request from `MeterRepository.list_all()` and
`TransformerRepository.list_all()`; no node table exists. At the current scale (403 meters)
that takes milliseconds. Beyond roughly 100k meters, persist the nodes at sync time instead.

Rules (ADR-005/006/007):
- a node's id is the "/"-joined codes from zone down to it, so a code repeated under another
  parent is a different node;
- a level with exactly one blank half is repaired (sibling meters first, then the number rule)
  and every repair is recorded; a meter that cannot be repaired is "unplaced" and attached to
  its deepest complete ancestor;
- a node's name is the DT list's name (DTs only) or else the most frequent name among its
  meters (ties: alphabetically first); every other name is kept as an alias.
"""

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from app.domain.models import HIERARCHY_LEVELS, HierarchyLevel, Meter, NodeRef, Transformer
from app.services.hierarchy.levels import code_from_name, name_from_code

RepairField = Literal["code", "name"]
RepairMethod = Literal["sibling", "number_rule", "dt_list"]


@dataclass(frozen=True)
class AltName:
    """A non-canonical name seen for a node, with the meters that used it."""

    name: str
    meter_ids: tuple[str, ...]


@dataclass(frozen=True)
class Repair:
    """One blank hierarchy half that was filled in for a meter.

    method: "sibling" (other meters of the same node), "number_rule" (code <-> name pattern),
    "dt_list" (a blank DT name filled from the DT list).
    """

    meter_id: str
    level: HierarchyLevel
    field: RepairField
    before: None
    after: str
    method: RepairMethod


@dataclass(frozen=True)
class ParentConflict:
    """One DT code seen under several parent paths (DT codes are globally unique)."""

    code: str
    paths: list[str]
    meter_ids: tuple[str, ...]


@dataclass(frozen=True)
class Node:
    """One tree node. `meter_ids` are the meters attached directly to it (every meter of a DT;
    for other levels only unplaced ones); `status_counts` cover the whole subtree."""

    id: str
    level: HierarchyLevel
    code: str
    name: str
    alt_names: tuple[AltName, ...]
    parent_id: str | None
    child_ids: tuple[str, ...]
    meter_ids: tuple[str, ...]
    status_counts: Mapping[str, int]
    unplaced_count: int = 0  # meters attached here because a lower level was unfixable

    @property
    def meter_count(self) -> int:
        """Meters in the whole subtree: sum of children's meter_count + unplaced_count
        (+ the meters of a DT)."""
        return sum(self.status_counts.values())


@dataclass(frozen=True)
class HierarchySnapshot:
    nodes: Mapping[str, Node]
    roots: tuple[str, ...]
    repairs: tuple[Repair, ...]
    conflicts: tuple[ParentConflict, ...]
    unplaced: tuple[str, ...]
    meters_without_hierarchy: tuple[str, ...]


def _blank(text: str | None) -> bool:
    return text is None or not text.strip()


def _clean(text: str | None) -> str | None:
    """Trim padding; blank becomes None."""
    return None if _blank(text) else (text or "").strip()


def _canonical(votes: Mapping[str, int]) -> str:
    """Most frequent name; ties go to the alphabetically first."""
    return min(votes, key=lambda name: (-votes[name], name))


def _join(parent_id: str | None, code: str) -> str:
    return code if parent_id is None else f"{parent_id}/{code}"


@dataclass(frozen=True)
class _Resolved:
    ref: NodeRef
    repair: Repair | None


def build_hierarchy(
    meters: Sequence[Meter], transformers: Sequence[Transformer]
) -> HierarchySnapshot:
    """Place every meter in the tree, repairing blanks and reporting conflicts."""
    dt_names = {t.code: t.name for t in transformers}
    ordered = sorted(meters, key=lambda m: m.meter_id)
    without = tuple(m.meter_id for m in ordered if m.hierarchy is None)
    parent_of: dict[str, str | None] = {m.meter_id: None for m in ordered if m.hierarchy}
    live = [m for m in ordered if m.hierarchy is not None]

    info: dict[str, tuple[HierarchyLevel, str, str | None]] = {}  # id -> level, code, parent
    attached: dict[str, list[str]] = defaultdict(list)
    seen_names: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    repairs: list[Repair] = []
    unplaced: list[str] = []

    for level in HIERARCHY_LEVELS:
        refs = {
            m.meter_id: NodeRef(_clean(ref.code), _clean(ref.name))
            for m in live
            if m.hierarchy is not None
            for ref in (m.hierarchy.get(level),)
        }
        code_votes: dict[tuple[str | None, str], Counter[str]] = defaultdict(Counter)
        name_votes: dict[tuple[str | None, str], Counter[str]] = defaultdict(Counter)
        for meter_id, ref in refs.items():
            if not _blank(ref.code) and not _blank(ref.name):
                key_parent = parent_of[meter_id]
                code_votes[(key_parent, ref.name or "")][ref.code or ""] += 1
                name_votes[(key_parent, ref.code or "")][ref.name or ""] += 1

        still_live: list[Meter] = []
        for meter in live:
            ref = refs[meter.meter_id]
            parent = parent_of[meter.meter_id]
            code, name = ref.code, ref.name
            repair: Repair | None = None
            if _blank(code) and not _blank(name):
                votes = code_votes.get((parent, name or ""))
                if votes:
                    top = max(votes.values())
                    code = min(c for c, n in votes.items() if n == top)
                    repair = Repair(meter.meter_id, level, "code", None, code, "sibling")
                elif (rule_code := code_from_name(level, name or "")) is not None:
                    code = rule_code
                    repair = Repair(meter.meter_id, level, "code", None, code, "number_rule")
            elif _blank(name) and not _blank(code):
                method: RepairMethod
                known = name_votes.get((parent, code or ""))
                listed = dt_names.get(code or "") if level is HierarchyLevel.DT else None
                if listed is not None:
                    name, method = listed, "dt_list"
                elif known:
                    name, method = _canonical(known), "sibling"
                else:
                    name, method = name_from_code(level, code or ""), "number_rule"
                if name is not None:
                    repair = Repair(meter.meter_id, level, "name", None, name, method)
            if _blank(code) or _blank(name):
                unplaced.append(meter.meter_id)
                if parent is not None:
                    attached[parent].append(meter.meter_id)
                continue
            assert code is not None and name is not None
            if repair is not None:
                repairs.append(repair)
            node_id = _join(parent, code)
            info[node_id] = (level, code, parent)
            seen_names[node_id][name].append(meter.meter_id)
            parent_of[meter.meter_id] = node_id
            still_live.append(meter)
        live = still_live

    for meter in live:
        attached[parent_of[meter.meter_id] or ""].append(meter.meter_id)

    return _assemble(info, attached, seen_names, dt_names, repairs, unplaced, without, meters)


def _assemble(
    info: dict[str, tuple[HierarchyLevel, str, str | None]],
    attached: dict[str, list[str]],
    seen_names: dict[str, dict[str, list[str]]],
    dt_names: Mapping[str, str],
    repairs: list[Repair],
    unplaced: list[str],
    without: tuple[str, ...],
    meters: Sequence[Meter],
) -> HierarchySnapshot:
    status = {m.meter_id: m.install_status.value for m in meters}
    children: dict[str | None, list[str]] = defaultdict(list)
    for node_id, (_, _code, parent) in info.items():
        children[parent].append(node_id)
    for siblings in children.values():
        siblings.sort(key=lambda i: info[i][1])

    counts: dict[str, Counter[str]] = {}
    for node_id in sorted(info, key=lambda i: -i.count("/")):
        total = Counter(status[m] for m in attached.get(node_id, ()))
        for child in children.get(node_id, ()):
            total.update(counts[child])
        counts[node_id] = total

    nodes: dict[str, Node] = {}
    for node_id, (level, code, parent) in info.items():
        names = seen_names[node_id]
        listed = dt_names.get(code) if level is HierarchyLevel.DT else None
        name = (
            listed if listed is not None else _canonical({n: len(ids) for n, ids in names.items()})
        )
        alts = tuple(
            AltName(n, tuple(sorted(ids))) for n, ids in sorted(names.items()) if n != name
        )
        nodes[node_id] = Node(
            id=node_id,
            level=level,
            code=code,
            name=name,
            alt_names=alts,
            parent_id=parent,
            child_ids=tuple(children.get(node_id, ())),
            meter_ids=tuple(sorted(attached.get(node_id, ()))),
            unplaced_count=0 if level is HierarchyLevel.DT else len(attached.get(node_id, ())),
            status_counts={k: v for k, v in sorted(counts[node_id].items()) if v},
        )

    by_code: dict[str, list[Node]] = defaultdict(list)
    for node in nodes.values():
        if node.level is HierarchyLevel.DT:
            by_code[node.code].append(node)
    conflicts = tuple(
        ParentConflict(
            code,
            sorted(n.parent_id for n in dts if n.parent_id is not None),
            tuple(sorted(m for n in dts for m in n.meter_ids)),
        )
        for code, dts in sorted(by_code.items())
        if len({n.parent_id for n in dts}) > 1
    )
    return HierarchySnapshot(
        nodes=dict(sorted(nodes.items())),
        roots=tuple(children.get(None, ())),
        repairs=tuple(repairs),
        conflicts=conflicts,
        unplaced=tuple(unplaced),
        meters_without_hierarchy=without,
    )


def subtree_meter_ids(snapshot: HierarchySnapshot, node_id: str) -> list[str]:
    """Every meter under the node (itself and all descendants), sorted."""
    found: list[str] = []
    stack = [node_id]
    while stack:
        node = snapshot.nodes[stack.pop()]
        found.extend(node.meter_ids)
        stack.extend(node.child_ids)
    return sorted(found)
