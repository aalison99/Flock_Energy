"""Builds the /api/v1 router by including every v1 sub-router."""

from fastapi import APIRouter

from app.api.v1.routers import health
from app.api.v1.schemas.common import ERROR_RESPONSES

api_router = APIRouter(prefix="/api/v1", responses=ERROR_RESPONSES)
api_router.include_router(health.router)
