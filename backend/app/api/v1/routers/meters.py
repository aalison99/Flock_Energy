"""Meter endpoints: search/list and detail."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.api.v1.params import MAX_REPEATED, meter_filter_params
from app.api.v1.schemas.common import error_responses
from app.api.v1.schemas.meters import (
    FacetsResponse,
    MeterDetail,
    MeterSummary,
    to_facets_response,
    to_meter_detail,
    to_meter_summary,
)
from app.core.deps import get_meter_service
from app.core.pagination import Page, PageParams, paginate
from app.domain.models import PageResult
from app.services.interfaces import FacetField, MeterFilters
from app.services.meter_service import MeterService

router = APIRouter(tags=["meters"])


@router.get(
    "/meters",
    operation_id="listMeters",
    response_model=Page[MeterSummary],
    summary="List meters",
    description=(
        "Paginated meter list. Filters combine (all must match). While the local index is "
        "empty only `q` and the default sort are served, from the live portal; other "
        "filters then answer 409."
    ),
    responses=error_responses(409, 422, 502, 503),
)
async def list_meters(
    service: Annotated[MeterService, Depends(get_meter_service)],
    params: Annotated[PageParams, Depends()],
    filters: Annotated[MeterFilters, Depends(meter_filter_params)],
) -> Page[MeterSummary]:
    result = await service.list_meters(filters, params.page, params.page_size)
    summaries = PageResult(items=[to_meter_summary(m) for m in result.items], total=result.total)
    return paginate(summaries, params.page, params.page_size)


@router.get(
    "/meters/facets",
    operation_id="getMeterFacets",
    response_model=FacetsResponse,
    summary="Count meters per attribute value",
    description=(
        "Counts for filter chips. Each field's counts apply every filter except that "
        "field's own, so the alternatives stay visible. Meters lacking a value (no install "
        "type or DT) are not counted, so a field's counts may not sum to the total. "
        "Needs the local index."
    ),
    responses=error_responses(409, 422),
)
async def get_meter_facets(
    service: Annotated[MeterService, Depends(get_meter_service)],
    filters: Annotated[MeterFilters, Depends(meter_filter_params)],
    field: Annotated[
        list[FacetField] | None,
        Query(
            max_length=MAX_REPEATED,
            description="Field to count; repeat for several. Default: all five.",
        ),
    ] = None,
) -> FacetsResponse:
    fields = field or list(FacetField)
    return to_facets_response(await service.facets(filters, fields))


@router.get(
    "/meters/{meter_id}",
    operation_id="getMeter",
    response_model=MeterDetail,
    summary="Get a meter",
    description="Full meter record with hierarchy, geo position and freshness metadata.",
    responses=error_responses(404, 422, 502, 503),
)
async def get_meter(
    service: Annotated[MeterService, Depends(get_meter_service)],
    meter_id: Annotated[
        str, Path(pattern=r"^J\d{6}$", description="Meter id, J followed by six digits.")
    ],
) -> MeterDetail:
    return to_meter_detail(await service.get_meter(meter_id))
