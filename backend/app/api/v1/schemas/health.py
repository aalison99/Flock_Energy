"""Readiness response schema."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.services.results import ReadinessResult


class PortalReadiness(BaseModel):
    """State of the upstream portal as seen by the service."""

    breaker: Literal["closed", "open", "half_open"] = Field(
        description="Circuit breaker state of the portal client."
    )


class IndexReadiness(BaseModel):
    """State of the local SQLite index (filled by the sync)."""

    ready: bool = Field(description="True once the index holds at least one meter.")
    meter_count: int = Field(description="Number of meters in the index.")
    last_sync_at: datetime | None = Field(
        description="When the last successful sync finished; null if none has."
    )


class ReadinessResponse(BaseModel):
    """Readiness probe payload; also the body of the 503 'not ready' answer."""

    status: Literal["ready", "not_ready"] = Field(
        description="Whether the service accepts traffic."
    )
    portal: PortalReadiness = Field(description="Portal connectivity details.")
    index: IndexReadiness = Field(
        description="Local index state; an empty index does not make the service not ready."
    )


def to_readiness_response(result: ReadinessResult) -> ReadinessResponse:
    return ReadinessResponse(
        status="ready" if result.ready else "not_ready",
        portal=PortalReadiness.model_validate({"breaker": result.breaker.value}),
        index=IndexReadiness(
            ready=result.index.ready,
            meter_count=result.index.meter_count,
            last_sync_at=result.index.last_sync_at,
        ),
    )
