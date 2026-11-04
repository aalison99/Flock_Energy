"""Meter endpoints: search/list and detail."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.api.v1.schemas.common import error_responses
from app.api.v1.schemas.meters import MeterDetail, MeterSummary, to_meter_detail, to_meter_summary
from app.core.deps import get_meter_service
from app.core.pagination import Page, PageParams, paginate
from app.domain.models import PageResult
from app.services.interfaces import MeterFilters
from app.services.meter_service import MeterService

router = APIRouter(tags=["meters"])


@router.get(
    "/meters",
    operation_id="listMeters",
    response_model=Page[MeterSummary],
    summary="List meters",
    description="Paginated meter list, optionally narrowed by a search text on id or serial.",
    responses=error_responses(422, 502, 503),
)
async def list_meters(
    service: Annotated[MeterService, Depends(get_meter_service)],
    params: Annotated[PageParams, Depends()],
    q: Annotated[
        str | None,
        Query(max_length=64, description="Search text matched against meter id and serial."),
    ] = None,
) -> Page[MeterSummary]:
    result = await service.list_meters(MeterFilters(q=q), params.page, params.page_size)
    summaries = PageResult(items=[to_meter_summary(m) for m in result.items], total=result.total)
    return paginate(summaries, params.page, params.page_size)


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
