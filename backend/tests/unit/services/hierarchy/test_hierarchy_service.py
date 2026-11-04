import pytest

from app.domain.exceptions import IndexNotReadyError, NotFoundError
from app.domain.models import HierarchyLevel, InstallStatus
from app.services.hierarchy_service import HierarchyService
from tests.support.fakes import FakeMeterRepository, FakeTransformerRepository
from tests.support.hierarchy_factory import make_meter, make_transformer

pytestmark = pytest.mark.anyio

DT1 = "Z-01/C-01/D-01/SD-01/SS-01/F-001/DT-001"


@pytest.fixture
def service() -> HierarchyService:
    meters = [
        make_meter("J1", status=InstallStatus.INSTALLED),
        make_meter("J2", status=InstallStatus.FAULTY),
        make_meter("J3", status=InstallStatus.FAULTY, dt=("DT-001", "Other")),
        make_meter("J4", circle=("C-02", "Circle 2"), dt=("DT-009", "Nine")),
        make_meter("J5", circle=("C-02", "Circle 2"), dt=("DT-009", "Nine")),
    ]
    return HierarchyService(
        FakeMeterRepository(meters), FakeTransformerRepository([make_transformer()])
    )


async def test_empty_index_is_not_ready() -> None:
    empty = HierarchyService(FakeMeterRepository([]), FakeTransformerRepository([]))
    for call in (empty.tree(2), empty.node("Z-01"), empty.meters_under("Z-01", 1, 10)):
        with pytest.raises(IndexNotReadyError):
            await call


async def test_tree_depth_one_has_only_zones_with_counts(service: HierarchyService) -> None:
    (zone,) = await service.tree(1)
    assert (zone.id, zone.level, zone.code, zone.meter_count) == (
        "Z-01",
        HierarchyLevel.ZONE,
        "Z-01",
        5,
    )
    assert zone.children == []
    assert zone.status_breakdown == {"installed": 3, "faulty": 2, "decommissioned": 0, "unknown": 0}


async def test_tree_depth_limits_levels(service: HierarchyService) -> None:
    (zone,) = await service.tree(2)
    assert [c.id for c in zone.children] == ["Z-01/C-01", "Z-01/C-02"]
    assert all(c.children == [] for c in zone.children)
    (full,) = await service.tree(7)
    node = full
    while node.children:
        node = node.children[0]
    assert node.level is HierarchyLevel.DT and node.id == DT1


async def test_node_detail(service: HierarchyService) -> None:
    detail = await service.node(DT1)
    assert [p.level for p in detail.path] == list(HierarchyLevel)
    assert detail.path[0].id == "Z-01" and detail.path[-1].id == DT1
    assert (detail.id, detail.code, detail.name) == (DT1, "DT-001", "Some DT 1")
    assert detail.meter_count == 3
    assert detail.status_breakdown["faulty"] == 2
    assert [(a.name, a.meter_ids) for a in detail.alt_names] == [("Other", ("J3",))]
    assert detail.children == []


async def test_node_detail_lists_children_with_counts(service: HierarchyService) -> None:
    detail = await service.node("Z-01")
    assert [(c.id, c.meter_count) for c in detail.children] == [("Z-01/C-01", 3), ("Z-01/C-02", 2)]
    assert detail.path[0].id == "Z-01" and len(detail.path) == 1


async def test_unknown_node_is_not_found(service: HierarchyService) -> None:
    with pytest.raises(NotFoundError, match="hierarchy node Z-09 not found"):
        await service.node("Z-09")
    with pytest.raises(NotFoundError):
        await service.meters_under("Z-09", 1, 10)


async def test_meters_under_pages_the_subtree_by_meter_id(service: HierarchyService) -> None:
    first = await service.meters_under("Z-01", 1, 2)
    assert (first.total, [m.meter_id for m in first.items]) == (5, ["J1", "J2"])
    last = await service.meters_under("Z-01", 3, 2)
    assert [m.meter_id for m in last.items] == ["J5"]
    beyond = await service.meters_under("Z-01", 9, 2)
    assert (beyond.total, list(beyond.items)) == (5, [])
