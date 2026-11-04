"""Builds the /api/v1 router by including every v1 sub-router."""

from fastapi import APIRouter

from app.api.v1.routers import (
    analytics,
    data_quality,
    geo,
    health,
    hierarchy,
    meters,
    readings,
    sync,
    transformers,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(analytics.router)
api_router.include_router(data_quality.router)
api_router.include_router(geo.router)
api_router.include_router(health.router)
api_router.include_router(hierarchy.router)
api_router.include_router(meters.router)
api_router.include_router(readings.router)
api_router.include_router(sync.router)
api_router.include_router(transformers.router)
