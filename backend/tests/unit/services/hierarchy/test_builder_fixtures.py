"""The builder on the real 403-meter fixture set (PROTOCOL section 4)."""

from collections import Counter

import pytest

from app.domain.models import HierarchyLevel, Meter, Transformer
from app.portal.fake import FakePortalClient
from app.services.hierarchy.builder import AltName, HierarchySnapshot, build_hierarchy
from tests.support.hierarchy_factory import assert_children_sum_to_parent
from tests.support.portal_emulator import FIXTURES

pytestmark = pytest.mark.anyio


@pytest.fixture
async def meters() -> list[Meter]:
    return await FakePortalClient(FIXTURES).bulk_export()


@pytest.fixture
async def transformers() -> list[Transformer]:
    portal = FakePortalClient(FIXTURES)
    found: list[Transformer] = []
    page = 1
    while True:
        result = await portal.list_transformers(page)
        found.extend(result.items)
        if len(result.items) < 20 or len(found) >= result.total:
            return found
        page += 1


@pytest.fixture
async def snap(meters: list[Meter], transformers: list[Transformer]) -> HierarchySnapshot:
    return build_hierarchy(meters, transformers)


async def test_node_counts_per_level(snap: HierarchySnapshot) -> None:
    counts = Counter(n.level for n in snap.nodes.values())
    assert [counts[level] for level in HierarchyLevel] == [3, 6, 30, 40, 40, 40, 40]


async def test_22_repairs_one_per_meter_with_expected_split(snap: HierarchySnapshot) -> None:
    assert len(snap.repairs) == 22
    assert len({r.meter_id for r in snap.repairs}) == 22
    assert Counter(r.level for r in snap.repairs) == {
        HierarchyLevel.CIRCLE: 11,
        HierarchyLevel.FEEDER: 8,
        HierarchyLevel.SUBSTATION: 3,
    }
    assert all(r.before is None for r in snap.repairs)


async def test_clean_data_has_no_conflicts_or_unplaced_meters(snap: HierarchySnapshot) -> None:
    assert snap.conflicts == ()
    assert snap.unplaced == ()
    assert snap.meters_without_hierarchy == ()


async def test_dt_007_alias_evidence(snap: HierarchySnapshot) -> None:
    (node,) = [n for n in snap.nodes.values() if n.code == "DT-007"]
    assert node.name == "Sanganer DT 7"
    assert node.alt_names == (AltName("Old Malviya Nagar Xfmr", ("J100400", "J100401", "J100402")),)
    assert len(node.meter_ids) == 13


async def test_only_dt_007_has_aliases(snap: HierarchySnapshot) -> None:
    assert [n.code for n in snap.nodes.values() if n.alt_names] == ["DT-007"]


async def test_every_meter_lands_in_exactly_one_dt(
    snap: HierarchySnapshot, meters: list[Meter]
) -> None:
    placed = [m for n in snap.nodes.values() for m in n.meter_ids]
    assert sorted(placed) == sorted(m.meter_id for m in meters)
    assert sum(snap.nodes[z].status_counts.get("installed", 0) for z in snap.roots) == 238


async def test_status_counts_sum_over_children(
    snap: HierarchySnapshot, meters: list[Meter]
) -> None:
    assert_children_sum_to_parent(snap, meters)
    assert sum(sum(snap.nodes[z].status_counts.values()) for z in snap.roots) == 403
