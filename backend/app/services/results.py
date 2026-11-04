"""Service result types: plain frozen dataclasses (no pydantic)."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from app.domain.models import GeoPoint, Meter
from app.portal.interfaces import BreakerState


@dataclass(frozen=True)
class Meta:
    """Where an answer came from and how fresh it is."""

    source: Literal["portal"]
    fetched_at: datetime
    stale: bool


@dataclass(frozen=True)
class MeterDetailResult:
    meter: Meter
    geo: GeoPoint | None
    meta: Meta


@dataclass(frozen=True)
class ReadinessResult:
    ready: bool
    breaker: BreakerState
