"""Application factory: wires settings, middleware, error handlers and routers."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1.router import api_router
from app.core.config import Settings, load_settings
from app.core.deps import wire
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware


def create_app(settings: Settings) -> FastAPI:
    """Build a fully wired app from explicit settings (no global state)."""
    configure_logging(settings.log_level)
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )
    wire(app, settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)
    app.include_router(api_router)
    return app


def create_app_from_env() -> FastAPI:
    """Factory for uvicorn: `uvicorn app.main:create_app_from_env --factory`."""
    return create_app(load_settings())
