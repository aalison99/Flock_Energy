"""Fleet analytics endpoints: summary, consumption, top consumers, anomalies, DT load."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Query

from app.api.v1.params import OptionalNodeId
from app.api.v1.schemas.analytics import (
    AnomalyListResponse,
    ConsumptionResponse,
    FleetSummaryOut,
    MeterAnomaliesResponse,
    TopConsumersResponse,
    TransformerLoadResponse,
    to_anomaly_out,
    to_consumption_response,
    to_fleet_summary_out,
    to_rule_out,
    to_top_consumers_response,
    to_transformer_load_response,
)
from app.api.v1.schemas.common import error_responses
from app.core.deps import get_analytics_service
from app.core.pagination import PageParams, paginate
from app.domain.models import PageResult
from app.services.analytics_service import AnalyticsService
from app.services.quality.models import Severity
from app.services.readings.buckets import Resolution

router = APIRouter(tags=["analytics"])

MeterId = Annotated[
    str, Path(pattern=r"^J\d{6}$", description="Meter id, J followed by six digits.")
]


@router.get(
    "/analytics/summary",
    operation_id="getFleetSummary",
    response_model=FleetSummaryOut,
    summary="Get the fleet summary",
    description=(
        "Meter counts by status, reporting versus silent meters, total consumption, the reading "
        "window and anomaly counts per rule, computed from the indexed readings. Needs the "
        "local index."
    ),
    responses=error_responses(409),
)
async def get_fleet_summary(
    service: Annotated[AnalyticsService, Depends(get_analytics_service)],
) -> FleetSummaryOut:
    return to_fleet_summary_out(await service.summary())


@router.get(
    "/analytics/consumption",
    operation_id="getConsumption",
    response_model=ConsumptionResponse,
    summary="Get consumption per hour or day",
    description=(
        "Energy summed across the meters of a hierarchy node (default: the whole fleet). Meters "
        "reporting less often than the resolution are left out and counted in "
        "`meters_excluded_coarser`. Needs the local index."
    ),
    responses=error_responses(404, 409, 422),
)
async def get_consumption(
    service: Annotated[AnalyticsService, Depends(get_analytics_service)],
    node: OptionalNodeId = None,
    resolution: Annotated[Literal["hourly", "daily"], Query(description="Bucket width.")] = "daily",
) -> ConsumptionResponse:
    return to_consumption_response(await service.consumption(node, Resolution(resolution)))


@router.get(
    "/analytics/top-consumers",
    operation_id="getTopConsumers",
    response_model=TopConsumersResponse,
    summary="List the top consuming meters",
    description=(
        "Reporting meters by total kWh, highest first, ties by meter id. Needs the local index."
    ),
    responses=error_responses(404, 409, 422),
)
async def get_top_consumers(
    service: Annotated[AnalyticsService, Depends(get_analytics_service)],
    node: OptionalNodeId = None,
    limit: Annotated[int, Query(ge=1, le=100, description="Meters to return (1 to 100).")] = 10,
) -> TopConsumersResponse:
    return to_top_consumers_response(await service.top_consumers(node, limit))


@router.get(
    "/analytics/anomalies",
    operation_id="listAnomalies",
    response_model=AnomalyListResponse,
    summary="List meter anomalies",
    description=(
        "Findings from every registered rule over the indexed readings, ordered by severity "
        "(error, warning, info), then meter id, then time. `rules` lists every rule. "
        "Needs the local index."
    ),
    responses=error_responses(404, 409, 422),
)
async def list_anomalies(
    service: Annotated[AnalyticsService, Depends(get_analytics_service)],
    params: Annotated[PageParams, Depends()],
    node: OptionalNodeId = None,
    rule: Annotated[str | None, Query(max_length=64, description="Only this rule id.")] = None,
    severity: Annotated[Severity | None, Query(description="Only this severity.")] = None,
) -> AnomalyListResponse:
    report = await service.anomalies(rule, severity, node, params.page, params.page_size)
    items = PageResult(
        items=[to_anomaly_out(a) for a in report.items.items], total=report.items.total
    )
    page = paginate(items, params.page, params.page_size)
    return AnomalyListResponse(
        **page.model_dump(exclude={"items"}),
        items=page.items,
        rules=[to_rule_out(r) for r in report.rules],
    )


@router.get(
    "/analytics/transformers/load",
    operation_id="getTransformerLoad",
    response_model=TransformerLoadResponse,
    summary="Estimate distribution transformer loading",
    description=(
        "Estimated peak and average kVA per DT from its half-hourly meters, against rated "
        "capacity. An estimate: see `estimate_note`. Needs the local index."
    ),
    responses=error_responses(409, 422),
)
async def get_transformer_load(
    service: Annotated[AnalyticsService, Depends(get_analytics_service)],
    sort: Annotated[
        Literal["utilisation", "code"],
        Query(description="utilisation: highest first, no data last; code: ascending."),
    ] = "utilisation",
    limit: Annotated[int, Query(ge=1, le=100, description="DTs to return (1 to 100).")] = 40,
) -> TransformerLoadResponse:
    return to_transformer_load_response(await service.transformer_load(sort, limit))


@router.get(
    "/meters/{meter_id}/anomalies",
    operation_id="getMeterAnomalies",
    response_model=MeterAnomaliesResponse,
    summary="List one meter's anomalies",
    description="Every rule finding for the meter, most severe first. Needs the local index.",
    responses=error_responses(404, 409, 422),
)
async def get_meter_anomalies(
    service: Annotated[AnalyticsService, Depends(get_analytics_service)],
    meter_id: MeterId,
) -> MeterAnomaliesResponse:
    found = await service.meter_anomalies(meter_id)
    return MeterAnomaliesResponse(meter_id=meter_id, items=[to_anomaly_out(a) for a in found])
