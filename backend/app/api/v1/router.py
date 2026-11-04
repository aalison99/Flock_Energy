"""Builds the /api/v1 router by including every v1 sub-router."""

from fastapi import APIRouter

from app.api.v1.routers import health, meters, transformers

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(meters.router)
api_router.include_router(transformers.router)
