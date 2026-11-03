"""Schemas shared by all v1 endpoints: the error envelope and the health payload."""

from typing import Literal

from pydantic import BaseModel


class ErrorBody(BaseModel):
    """The inner object of the error envelope."""

    code: str
    message: str
    details: dict[str, object]


class ErrorResponse(BaseModel):
    """The single error shape returned by every failing endpoint."""

    error: ErrorBody


class HealthResponse(BaseModel):
    """Liveness probe payload."""

    status: Literal["ok"]
    version: str


ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    status: {"model": ErrorResponse, "description": description}
    for status, description in {
        404: "Not found",
        409: "Conflict or index not ready",
        422: "Validation failed",
        500: "Internal server error",
        502: "Portal auth or protocol failure",
        503: "Portal unavailable",
    }.items()
}
