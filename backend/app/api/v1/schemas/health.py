"""Readiness response schema."""

from typing import Literal

from pydantic import BaseModel, Field

from app.services.results import ReadinessResult


class PortalReadiness(BaseModel):
    """State of the upstream portal as seen by the service."""

    breaker: Literal["closed", "open", "half_open"] = Field(
        description="Circuit breaker state of the portal client."
    )


class ReadinessResponse(BaseModel):
    """Readiness probe payload; also the body of the 503 'not ready' answer."""

    status: Literal["ready", "not_ready"] = Field(
        description="Whether the service accepts traffic."
    )
    portal: PortalReadiness = Field(description="Portal connectivity details.")


def to_readiness_response(result: ReadinessResult) -> ReadinessResponse:
    return ReadinessResponse(
        status="ready" if result.ready else "not_ready",
        portal=PortalReadiness.model_validate({"breaker": result.breaker.value}),
    )
