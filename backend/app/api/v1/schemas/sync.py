"""Sync request and response schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.config import JsonDict

from app.domain.models import SyncRun
from app.services.results import SyncStatusResult

_RUN_EXAMPLE: JsonDict = {
    "id": 3,
    "status": "succeeded",
    "strategy": "export",
    "started_at": "2026-11-04T09:00:00Z",
    "finished_at": "2026-11-04T09:01:12Z",
    "counts": {
        "meters": 403,
        "meters_removed": 0,
        "transformers": 40,
        "transformers_removed": 0,
        "readings": 1250,
        "readings_meters": 403,
        "readings_failed": 0,
    },
    "error": None,
}


class SyncRequest(BaseModel):
    """Options for a sync run."""

    model_config = ConfigDict(json_schema_extra={"example": {"include_readings": True}})

    include_readings: bool = Field(
        default=True,
        description="Also fetch every meter's readings (slower); false syncs only the rest.",
    )


class SyncRunOut(BaseModel):
    """One attempt to refresh the local index from the portal."""

    model_config = ConfigDict(json_schema_extra={"example": _RUN_EXAMPLE})

    id: int = Field(description="Run id; later runs have larger ids.")
    status: Literal["running", "succeeded", "failed"] = Field(description="Where the run stands.")
    strategy: Literal["export", "crawl"] | None = Field(
        description="How meters were fetched: bulk export or per-meter crawl; null until known."
    )
    started_at: datetime = Field(description="When the run started (UTC).")
    finished_at: datetime | None = Field(description="When the run ended; null while running.")
    counts: dict[str, int] = Field(
        description="Progress counters: meters, meters_removed, transformers, "
        "transformers_removed, readings, readings_meters, readings_failed."
    )
    error: str | None = Field(description="Why the run failed; null otherwise.")


class SyncStatusResponse(BaseModel):
    """The latest sync run and the latest one that succeeded."""

    model_config = ConfigDict(
        json_schema_extra={"example": {"latest": _RUN_EXAMPLE, "last_successful": _RUN_EXAMPLE}}
    )

    latest: SyncRunOut | None = Field(description="The most recent run; null if none has run.")
    last_successful: SyncRunOut | None = Field(
        description="The most recent run that succeeded; null if none has."
    )


def to_sync_run_out(run: SyncRun) -> SyncRunOut:
    return SyncRunOut.model_validate(
        {
            "id": run.id,
            "status": run.status.value,
            "strategy": run.strategy.value if run.strategy else None,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "counts": dict(run.counts),
            "error": run.error,
        }
    )


def to_sync_status_response(result: SyncStatusResult) -> SyncStatusResponse:
    return SyncStatusResponse(
        latest=to_sync_run_out(result.latest) if result.latest else None,
        last_successful=to_sync_run_out(result.last_successful) if result.last_successful else None,
    )
