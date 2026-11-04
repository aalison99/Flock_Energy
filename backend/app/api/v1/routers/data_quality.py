"""Data-quality report endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.v1.schemas.common import error_responses
from app.api.v1.schemas.data_quality import (
    DataQualityResponse,
    to_check_out,
    to_issue_out,
)
from app.core.deps import get_data_quality_service
from app.core.pagination import PageParams, paginate
from app.domain.models import PageResult
from app.services.data_quality_service import DataQualityService
from app.services.quality.models import Severity

router = APIRouter(tags=["data-quality"])


@router.get(
    "/data-quality",
    operation_id="getDataQualityReport",
    response_model=DataQualityResponse,
    summary="Get the data-quality report",
    description=(
        "Findings from every registered check over the indexed data: name conflicts, repaired "
        "blanks, DT mismatches, missing or outlying positions. `summary` counts all issues per "
        "check regardless of filters. Needs the local index."
    ),
    responses=error_responses(409, 422),
)
async def get_data_quality_report(
    service: Annotated[DataQualityService, Depends(get_data_quality_service)],
    params: Annotated[PageParams, Depends()],
    check: Annotated[
        str | None, Query(max_length=64, description="Only issues from this check id.")
    ] = None,
    severity: Annotated[Severity | None, Query(description="Only issues of this severity.")] = None,
) -> DataQualityResponse:
    report = await service.report(check, severity, params.page, params.page_size)
    issues = PageResult(
        items=[to_issue_out(i) for i in report.items.items], total=report.items.total
    )
    page = paginate(issues, params.page, params.page_size)
    return DataQualityResponse(
        **page.model_dump(exclude={"items"}),
        items=page.items,
        summary=report.summary,
        checks=[to_check_out(c) for c in report.checks],
    )
