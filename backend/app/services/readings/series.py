"""Cumulative registers -> per-interval consumption (pure, no I/O)."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from itertools import pairwise
from math import ceil
from statistics import median
from typing import Literal

from app.domain.models import Reading

RESET = "register_reset"
GAP = "gap"
PF_OUT_OF_RANGE = "pf_out_of_range"

IntervalKind = Literal["half_hourly", "daily", "unknown"]
INTERVAL_KINDS: dict[int, IntervalKind] = {30: "half_hourly", 1440: "daily"}


@dataclass(frozen=True)
class IntervalPoint:
    """One reading plus the consumption over the interval ending at it."""

    at: datetime
    start: datetime | None
    kwh_register: float
    kvah_register: float
    voltage_r: float | None
    kwh: float | None
    kvah: float | None
    power_factor: float | None
    flags: tuple[str, ...]


def interval_kind(interval_minutes: int | None) -> IntervalKind:
    return INTERVAL_KINDS.get(interval_minutes, "unknown") if interval_minutes else "unknown"


def power_factor(kwh: float | None, kvah: float | None) -> float | None:
    """kWh / kVAh to 3 dp; None unless both are known and kVAh is positive."""
    if kwh is None or kvah is None or kvah <= 0:
        return None
    return round(kwh / kvah, 3)


def _ascending_unique(readings: Sequence[Reading]) -> list[Reading]:
    seen: set[datetime] = set()
    unique: list[Reading] = []
    for reading in sorted(readings, key=lambda x: x.at):  # stable: first duplicate wins
        if reading.at not in seen:
            seen.add(reading.at)
            unique.append(reading)
    return unique


def detect_interval(readings: Sequence[Reading]) -> int | None:
    """Median gap between consecutive readings in whole minutes; None under two readings."""
    ordered = _ascending_unique(readings)
    if len(ordered) < 2:
        return None
    gaps = [(b.at - a.at).total_seconds() / 60 for a, b in pairwise(ordered)]
    return int(median(gaps) + 0.5)  # half-up, never truncate


def missing_intervals(span_minutes: float, interval_minutes: int | None) -> int:
    """Intervals absent inside a span: ceil(span / interval) - 1; 0 when span <= interval."""
    if not interval_minutes or span_minutes <= interval_minutes:
        return 0
    return ceil(span_minutes / interval_minutes) - 1


def totals(points: Sequence[IntervalPoint]) -> tuple[float, float]:
    """(kWh, kVAh) consumed over the points, 3 dp; reset intervals (null deltas) add nothing."""
    kwh = sum(p.kwh for p in points if p.kwh is not None)
    kvah = sum(p.kvah for p in points if p.kvah is not None)
    return round(kwh, 3), round(kvah, 3)


def _first(reading: Reading) -> IntervalPoint:
    return IntervalPoint(
        reading.at, None, reading.kwh_register, reading.kvah_register, reading.voltage_r,
        None, None, None, (),
    )  # fmt: skip


def _next(prev: Reading, cur: Reading, interval_minutes: int | None) -> IntervalPoint:
    flags: set[str] = set()
    kwh: float | None = round(cur.kwh_register - prev.kwh_register, 3)
    kvah: float | None = round(cur.kvah_register - prev.kvah_register, 3)
    assert kwh is not None and kvah is not None
    if kwh < 0 or kvah < 0:
        kwh = kvah = None
        flags.add(RESET)
    pf = power_factor(kwh, kvah)
    if pf is not None and pf > 1:
        flags.add(PF_OUT_OF_RANGE)
    if missing_intervals((cur.at - prev.at).total_seconds() / 60, interval_minutes):
        flags.add(GAP)
    return IntervalPoint(
        cur.at, prev.at, cur.kwh_register, cur.kvah_register, cur.voltage_r,
        kwh, kvah, pf, tuple(sorted(flags)),
    )  # fmt: skip


def to_interval_points(
    readings: Sequence[Reading], interval_minutes: int | None
) -> list[IntervalPoint]:
    """One point per reading (ascending, de-duplicated); the first has no deltas."""
    ordered = _ascending_unique(readings)
    if not ordered:
        return []
    points = [_first(ordered[0])]
    points += [_next(a, b, interval_minutes) for a, b in pairwise(ordered)]
    return points
