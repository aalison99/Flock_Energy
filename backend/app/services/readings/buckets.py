"""Aggregate interval points into hourly/daily buckets (pure, no I/O)."""

from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from app.services.readings.series import PF_OUT_OF_RANGE, IntervalPoint, power_factor


class Resolution(StrEnum):
    RAW = "raw"
    HOURLY = "hourly"
    DAILY = "daily"


@dataclass(frozen=True)
class Bucket:
    start: datetime
    end: datetime
    kwh: float | None
    kvah: float | None
    power_factor: float | None
    avg_voltage: float | None
    readings: int
    flags: tuple[str, ...]


# Floors an instant to its bucket start in the instant's own (IST) timezone. RAW is not here.
BUCKETERS: Mapping[Resolution, Callable[[datetime], datetime]] = {
    Resolution.HOURLY: lambda t: t.replace(minute=0, second=0, microsecond=0),
    Resolution.DAILY: lambda t: t.replace(hour=0, minute=0, second=0, microsecond=0),
}

BUCKET_MINUTES: Mapping[Resolution, int] = {Resolution.HOURLY: 60, Resolution.DAILY: 1440}


def _sum(values: list[float]) -> float | None:
    return round(sum(values), 3) if values else None


def _make(start: datetime, width: int, members: list[IntervalPoint]) -> Bucket:
    kwh = _sum([p.kwh for p in members if p.kwh is not None])
    kvah = _sum([p.kvah for p in members if p.kvah is not None])
    volts = [p.voltage_r for p in members if p.voltage_r is not None]
    pf = power_factor(kwh, kvah)
    flags = {f for p in members for f in p.flags}
    if pf is not None and pf > 1:
        flags.add(PF_OUT_OF_RANGE)
    return Bucket(
        start=start,
        end=start + timedelta(minutes=width),
        kwh=kwh,
        kvah=kvah,
        power_factor=pf,
        avg_voltage=round(sum(volts) / len(volts), 1) if volts else None,
        readings=len(members),
        flags=tuple(sorted(flags)),
    )


def aggregate(points: Sequence[IntervalPoint], resolution: Resolution) -> list[Bucket]:
    """Group intervals by the bucket containing their start; ascending. RAW is not aggregable."""
    floor = BUCKETERS[resolution]
    groups: dict[datetime, list[IntervalPoint]] = defaultdict(list)
    for point in points:
        if point.start is not None:
            groups[floor(point.start)].append(point)
    width = BUCKET_MINUTES[resolution]
    return [_make(start, width, groups[start]) for start in sorted(groups)]
