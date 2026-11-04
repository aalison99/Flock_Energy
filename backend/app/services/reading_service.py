"""Readings use case: portal registers -> clean consumption series, buckets and a summary."""

from datetime import date

from app.core.interfaces import Clock
from app.domain.exceptions import ValidationError
from app.portal.interfaces import FreshnessReader, PortalClient
from app.services.readings.buckets import BUCKET_MINUTES, Resolution, aggregate
from app.services.readings.series import (
    RESET,
    IntervalPoint,
    detect_interval,
    interval_kind,
    missing_intervals,
    to_interval_points,
)
from app.services.results import Meta, ReadingSeriesResult, ReadingSummary


def _summarise(points: list[IntervalPoint], interval_minutes: int | None) -> ReadingSummary:
    volts = [p.voltage_r for p in points if p.voltage_r is not None]
    gaps = sum(
        missing_intervals((p.at - p.start).total_seconds() / 60, interval_minutes)
        for p in points
        if p.start is not None
    )
    return ReadingSummary(
        total_kwh=round(sum(p.kwh for p in points if p.kwh is not None), 3),
        total_kvah=round(sum(p.kvah for p in points if p.kvah is not None), 3),
        avg_voltage=round(sum(volts) / len(volts), 1) if volts else None,
        readings=len(points),
        gaps=gaps,
        resets=sum(1 for p in points if RESET in p.flags),
        first_at=points[0].at if points else None,
        last_at=points[-1].at if points else None,
    )


class ReadingService:
    def __init__(self, portal: PortalClient, freshness: FreshnessReader, clock: Clock) -> None:
        self._portal = portal
        self._freshness = freshness
        self._clock = clock

    async def get_readings(
        self, meter_id: str, start: date | None, end: date | None, resolution: Resolution
    ) -> ReadingSeriesResult:
        if start is not None and end is not None and start > end:
            raise ValidationError(
                "start must be on or before end",
                details={"start": start.isoformat(), "end": end.isoformat()},
            )
        readings = await self._portal.get_readings(meter_id, start, end)
        interval = detect_interval(readings)
        width = BUCKET_MINUTES.get(resolution)
        if interval is not None and width is not None and width < interval:
            raise ValidationError(
                f"resolution '{resolution}' is finer than this meter's {interval}-minute interval",
                details={"resolution": str(resolution), "interval_minutes": interval},
            )
        points = to_interval_points(readings, interval)
        raw = resolution is Resolution.RAW
        entry = self._freshness.freshness("get_readings", meter_id, start, end)
        meta = (
            Meta("portal", entry.fetched_at, entry.stale)
            if entry is not None
            else Meta("portal", self._clock.now(), False)
        )
        return ReadingSeriesResult(
            meter_id=meter_id,
            resolution=resolution,
            interval_minutes=interval,
            interval_kind=interval_kind(interval),
            points=points if raw else None,
            buckets=None if raw else aggregate(points, resolution),
            summary=_summarise(points, interval),
            meta=meta,
        )
