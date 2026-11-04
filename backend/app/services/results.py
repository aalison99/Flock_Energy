"""Service result types: plain frozen dataclasses (no pydantic)."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from app.domain.models import GeoPoint, Meter
from app.portal.interfaces import BreakerState
from app.services.readings.buckets import Bucket, Resolution
from app.services.readings.series import IntervalKind, IntervalPoint


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


@dataclass(frozen=True)
class ReadingSummary:
    total_kwh: float
    total_kvah: float
    avg_voltage: float | None
    readings: int
    gaps: int
    resets: int
    first_at: datetime | None
    last_at: datetime | None


@dataclass(frozen=True)
class ReadingSeriesResult:
    """Exactly one of `points` (raw) or `buckets` (hourly/daily) is set."""

    meter_id: str
    resolution: Resolution
    interval_minutes: int | None
    interval_kind: IntervalKind
    points: list[IntervalPoint] | None
    buckets: list[Bucket] | None
    summary: ReadingSummary
    meta: Meta
