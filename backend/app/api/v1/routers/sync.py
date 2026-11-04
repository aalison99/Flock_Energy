"""Sync endpoints: start a background refresh of the local index, and read its status."""

from typing import Annotated

from fastapi import APIRouter, Body, Depends

from app.api.v1.schemas.common import error_responses
from app.api.v1.schemas.sync import (
    SyncRequest,
    SyncRunOut,
    SyncStatusResponse,
    to_sync_run_out,
    to_sync_status_response,
)
from app.core.deps import get_sync_service
from app.services.sync_service import SyncService

router = APIRouter(tags=["sync"])


@router.post(
    "/sync",
    operation_id="startSync",
    response_model=SyncRunOut,
    status_code=202,
    summary="Start a sync",
    description=(
        "Starts refreshing the local index from the portal. The run continues in the "
        "background: poll GET /sync/status. Only one run at a time (409 otherwise)."
    ),
    responses=error_responses(409, 422),
)
async def start_sync(
    service: Annotated[SyncService, Depends(get_sync_service)],
    body: Annotated[SyncRequest | None, Body()] = None,
) -> SyncRunOut:
    options = body or SyncRequest()
    return to_sync_run_out(await service.start(options.include_readings))


@router.get(
    "/sync/status",
    operation_id="getSyncStatus",
    response_model=SyncStatusResponse,
    summary="Sync status",
    description="The latest sync run and the latest successful one; both null if never synced.",
)
async def get_sync_status(
    service: Annotated[SyncService, Depends(get_sync_service)],
) -> SyncStatusResponse:
    return to_sync_status_response(await service.status())
