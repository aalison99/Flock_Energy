"""Schemas shared by all v1 endpoints: the error envelope and the health payload."""

from typing import Literal

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    """The inner object of the error envelope."""

    code: str = Field(description="Stable machine-readable error code, e.g. not_found.")
    message: str = Field(description="Human-readable explanation.")
    details: dict[str, object] = Field(description="Extra context; empty when there is none.")


class ErrorResponse(BaseModel):
    """The single error shape returned by every failing endpoint."""

    error: ErrorBody = Field(description="The error.")


class HealthResponse(BaseModel):
    """Liveness probe payload."""

    status: Literal["ok"] = Field(description="Always ok while the process is up.")
    version: str = Field(description="Application version.")


_DESCRIPTIONS = {
    404: "Not found",
    422: "Validation failed",
    502: "Portal auth or protocol failure",
    503: "Portal unavailable",
}


_RETRY_AFTER = {
    "description": "Seconds to wait before retrying (present when the portal gave a hint).",
    "schema": {"type": "integer"},
}


def error_responses(*statuses: int) -> dict[int | str, dict[str, object]]:
    """OpenAPI `responses` entries for the given error statuses, all using the error envelope."""
    responses: dict[int | str, dict[str, object]] = {}
    for status in statuses:
        entry: dict[str, object] = {"model": ErrorResponse, "description": _DESCRIPTIONS[status]}
        if status == 503:
            entry["headers"] = {"Retry-After": _RETRY_AFTER}
        responses[status] = entry
    return responses
