"""One meter's readings, analysed once, shared by every analytic and rule (pure, no I/O).

The delta, gap, reset and interval maths all live in `services/readings/series.py`.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from app.domain.models import Meter, Reading
from app.services.readings.series import (
    IntervalKind,
    IntervalPoint,
    detect_interval,
    interval_kind,
    to_interval_points,
    totals,
)


@dataclass(frozen=True)
class MeterProfile:
    """A meter, its interval points and totals. "Reporting" = at least two readings."""

    meter: Meter
    points: list[IntervalPoint]
    interval_minutes: int | None
    interval_kind: IntervalKind
    total_kwh: float
    total_kvah: float
    first_at: datetime | None
    last_at: datetime | None

    @property
    def reporting(self) -> bool:
        return len(self.points) >= 2


def profile_meter(meter: Meter, readings: Sequence[Reading]) -> MeterProfile:
    interval = detect_interval(readings)
    points = to_interval_points(readings, interval)
    total_kwh, total_kvah = totals(points)
    return MeterProfile(
        meter=meter,
        points=points,
        interval_minutes=interval,
        interval_kind=interval_kind(interval),
        total_kwh=total_kwh,
        total_kvah=total_kvah,
        first_at=points[0].at if points else None,
        last_at=points[-1].at if points else None,
    )
