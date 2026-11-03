"""Error handling: maps domain and framework errors to one JSON envelope."""

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.domain.exceptions import (
    ConflictError,
    DomainError,
    IndexNotReadyError,
    NotFoundError,
    UpstreamAuthError,
    UpstreamProtocolError,
    UpstreamUnavailableError,
    ValidationError,
)

logger = logging.getLogger("urja.errors")

STATUS_BY_ERROR: dict[type[DomainError], int] = {
    ValidationError: 422,
    NotFoundError: 404,
    ConflictError: 409,
    IndexNotReadyError: 409,
    UpstreamAuthError: 502,
    UpstreamProtocolError: 502,
    UpstreamUnavailableError: 503,
}

_HTTP_CODES = {404: "not_found", 405: "method_not_allowed"}


def status_for(error: DomainError) -> int:
    """HTTP status for a domain error, walking the MRO; 500 when unmapped."""
    for cls in type(error).__mro__:
        if cls in STATUS_BY_ERROR:
            return STATUS_BY_ERROR[cls]
    return 500


def envelope(
    code: str, message: str, details: dict[str, object] | None = None
) -> dict[str, object]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def _domain_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DomainError)
    headers: dict[str, str] = {}
    if isinstance(exc, UpstreamUnavailableError) and exc.retry_after_s is not None:
        headers["Retry-After"] = str(exc.retry_after_s)
    status = status_for(exc)
    if status >= 500:
        logger.error("Domain error %s: %s", exc.code, exc.message, exc_info=exc)
    return JSONResponse(
        envelope(exc.code, exc.message, exc.details), status_code=status, headers=headers
    )


def _http_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code = _HTTP_CODES.get(exc.status_code, "http_error")
    return JSONResponse(
        envelope(code, str(exc.detail)), status_code=exc.status_code, headers=exc.headers
    )


def _validation_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    errors = [
        {"loc": list(e["loc"]), "msg": str(e["msg"]), "type": str(e["type"])} for e in exc.errors()
    ]
    return JSONResponse(
        envelope("validation_error", "Request validation failed", {"errors": errors}),
        status_code=422,
    )


def _cors_headers(request: Request) -> dict[str, str]:
    """CORS headers for an allowed Origin; the 500 handler runs outside CORSMiddleware."""
    origin = request.headers.get("origin")
    app = request.scope.get("app")
    settings = getattr(getattr(app, "state", None), "settings", None)
    allowed: list[str] = getattr(settings, "cors_origins", [])
    if origin and (origin in allowed or "*" in allowed):
        return {"Access-Control-Allow-Origin": origin, "Vary": "Origin"}
    return {}


def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "") or uuid.uuid4().hex
    logger.error("Unhandled exception", exc_info=exc)
    return JSONResponse(
        envelope("internal_error", "Internal server error", {"request_id": request_id}),
        status_code=500,
        headers={"X-Request-ID": request_id, **_cors_headers(request)},
    )


def register_error_handlers(app: FastAPI) -> None:
    """Install all exception handlers on the app."""
    app.add_exception_handler(DomainError, _domain_handler)
    app.add_exception_handler(StarletteHTTPException, _http_handler)
    app.add_exception_handler(RequestValidationError, _validation_handler)
    app.add_exception_handler(Exception, _unhandled_handler)
