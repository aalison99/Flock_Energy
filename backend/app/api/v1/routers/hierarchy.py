"""Network hierarchy endpoints: the tree, one node, and a node's meters."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.v1.schemas.common import error_responses
from app.api.v1.schemas.hierarchy import (
    NodeDetailOut,
    TreeResponse,
    to_node_detail_out,
    to_tree_node_out,
)
from app.api.v1.schemas.meters import MeterSummary, to_meter_summary
from app.core.deps import get_hierarchy_service
from app.core.pagination import Page, PageParams, paginate
from app.domain.models import PageResult
from app.services.hierarchy_service import HierarchyService

router = APIRouter(tags=["hierarchy"])

NodeId = Annotated[
    str,
    Query(
        pattern=r"^Z-\d{2}(/[A-Z]{1,2}-\d{2,3}){0,6}$",
        description=(
            "Node id: the codes from the zone down to the node joined by '/', "
            "e.g. Z-01/C-01/D-07/SD-07/SS-07/F-007/DT-007. Passed as a query parameter "
            "because it contains slashes."
        ),
    ),
]


@router.get(
    "/hierarchy",
    operation_id="getHierarchyTree",
    response_model=TreeResponse,
    summary="Get the network hierarchy tree",
    description=(
        "Zone, circle, division, subdivision, substation, feeder and DT, rebuilt from the "
        "indexed meters. Nodes are identified by their full code path. Needs the local index."
    ),
    responses=error_responses(409, 422),
)
async def get_hierarchy_tree(
    service: Annotated[HierarchyService, Depends(get_hierarchy_service)],
    depth: Annotated[
        int, Query(ge=1, le=7, description="Levels to include: 1 = zones only, 7 = down to DTs.")
    ] = 2,
) -> TreeResponse:
    return TreeResponse(items=[to_tree_node_out(n) for n in await service.tree(depth)])


@router.get(
    "/hierarchy/node",
    operation_id="getHierarchyNode",
    response_model=NodeDetailOut,
    summary="Get one hierarchy node",
    description="A node with its path from the zone, children, meter counts and alias names.",
    responses=error_responses(404, 409, 422),
)
async def get_hierarchy_node(
    service: Annotated[HierarchyService, Depends(get_hierarchy_service)],
    id: NodeId,
) -> NodeDetailOut:
    return to_node_detail_out(await service.node(id))


@router.get(
    "/hierarchy/node/meters",
    operation_id="listHierarchyNodeMeters",
    response_model=Page[MeterSummary],
    summary="List the meters under a hierarchy node",
    description="Paginated meters in the node's whole subtree, ordered by meter id.",
    responses=error_responses(404, 409, 422),
)
async def list_hierarchy_node_meters(
    service: Annotated[HierarchyService, Depends(get_hierarchy_service)],
    params: Annotated[PageParams, Depends()],
    id: NodeId,
) -> Page[MeterSummary]:
    result = await service.meters_under(id, params.page, params.page_size)
    summaries = PageResult(items=[to_meter_summary(m) for m in result.items], total=result.total)
    return paginate(summaries, params.page, params.page_size)
