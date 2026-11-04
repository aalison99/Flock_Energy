"""Readings endpoint: clean consumption series for one meter."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.api.v1.schemas.common import error_responses
from app.api.v1.schemas.readings import ReadingSeriesResponse, to_reading_series
from app.core.deps import get_reading_service
from app.services.reading_service import ReadingService
from app.services.readings.buckets import Resolution

router = APIRouter(tags=["readings"])


@router.get(
    "/meters/{meter_id}/readings",
    operation_id="getMeterReadings",
    response_model=ReadingSeriesResponse,
    summary="Get a meter's consumption series",
    description=(
        "Consumption per interval (or summed per hour/day) computed from the portal's cumulative "
        "registers. The portal holds a fixed snapshot (23-30 Jun 2026); ranges outside it return "
        "empty data."
    ),
    responses=error_responses(404, 422, 502, 503),
)
async def get_meter_readings(
    service: Annotated[ReadingService, Depends(get_reading_service)],
    meter_id: Annotated[
        str, Path(pattern=r"^J\d{6}$", description="Meter id, J followed by six digits.")
    ],
    start: Annotated[
        date | None,
        Query(
            description="First calendar day (IST, inclusive), YYYY-MM-DD. Default: no lower bound."
        ),
    ] = None,
    end: Annotated[
        date | None,
        Query(
            description="Last calendar day (IST, inclusive), YYYY-MM-DD. Default: no upper bound."
        ),
    ] = None,
    resolution: Annotated[
        Resolution,
        Query(description="raw = one point per reading; hourly or daily = summed buckets."),
    ] = Resolution.RAW,
) -> ReadingSeriesResponse:
    return to_reading_series(await service.get_readings(meter_id, start, end, resolution))
