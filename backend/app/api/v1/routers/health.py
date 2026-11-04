"""Health probes: liveness (static) and readiness (circuit-breaker based, no portal calls)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app import __version__
from app.api.v1.schemas.common import HealthResponse
from app.api.v1.schemas.health import ReadinessResponse, to_readiness_response
from app.core.deps import get_health_service
from app.services.health_service import HealthService

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    operation_id="getHealth",
    response_model=HealthResponse,
    summary="Liveness probe",
)
def health() -> HealthResponse:
    return HealthResponse(status="ok", version=__version__)


@router.get(
    "/health/ready",
    operation_id="getReadiness",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    description=(
        "Ready unless the portal circuit breaker is open; never calls the portal. "
        "Also reports the local index (an empty index is reported, not a failure)."
    ),
    responses={503: {"model": ReadinessResponse, "description": "Not ready: portal breaker open"}},
)
async def ready(
    service: Annotated[HealthService, Depends(get_health_service)], response: Response
) -> ReadinessResponse:
    result = await service.readiness()
    if not result.ready:
        response.status_code = 503
    return to_readiness_response(result)
