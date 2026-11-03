"""Liveness probe: a static endpoint proving the process is up."""

from fastapi import APIRouter

from app import __version__
from app.api.v1.schemas.common import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
def health() -> HealthResponse:
    return HealthResponse(status="ok", version=__version__)
