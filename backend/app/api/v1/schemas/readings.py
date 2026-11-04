"""Readings response schemas and the pure mapping from the service result."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.schemas.meters import MetaOut
from app.services.readings.buckets import Bucket, Resolution
from app.services.readings.series import IntervalKind, IntervalPoint
from app.services.results import ReadingSeriesResult, ReadingSummary


class ReadingPoint(BaseModel):
    """One portal reading with the consumption over the interval that ends at it."""

    at: datetime = Field(description="When the register was read (IST, ISO 8601 with +05:30).")
    interval_start: datetime | None = Field(
        description="Start of the interval ending at `at`; null for the first reading."
    )
    kwh_register: float = Field(description="Cumulative active-energy register (kWh).")
    kvah_register: float = Field(description="Cumulative apparent-energy register (kVAh).")
    voltage_r: float | None = Field(description="R-phase voltage (V), if reported.")
    kwh: float | None = Field(
        description="Active energy used in the interval (kWh, 3 dp); null for the first reading "
        "or after a register reset."
    )
    kvah: float | None = Field(description="Apparent energy used in the interval (kVAh, 3 dp).")
    power_factor: float | None = Field(
        description="kwh / kvah (3 dp); null when either is missing or kvah is not positive."
    )
    flags: list[str] = Field(
        description="Data-quality flags: register_reset, gap, pf_out_of_range."
    )


class ReadingBucket(BaseModel):
    """Consumption summed over an hour or a day (intervals belong to the bucket of their start)."""

    start: datetime = Field(description="Bucket start (IST), inclusive.")
    end: datetime = Field(description="Bucket end (IST), exclusive.")
    kwh: float | None = Field(description="Sum of interval kWh; null when no interval has a value.")
    kvah: float | None = Field(description="Sum of interval kVAh; null when none has a value.")
    power_factor: float | None = Field(description="kwh / kvah of the sums (3 dp), if defined.")
    avg_voltage: float | None = Field(description="Mean R-phase voltage (V, 1 dp), if reported.")
    readings: int = Field(description="Number of intervals attributed to this bucket.")
    flags: list[str] = Field(description="Sorted union of the member intervals' flags.")


class ReadingSummaryOut(BaseModel):
    """Totals and data-quality counts over the whole returned range."""

    total_kwh: float = Field(description="Total active energy (kWh); resets are excluded.")
    total_kvah: float = Field(description="Total apparent energy (kVAh); resets are excluded.")
    avg_voltage: float | None = Field(description="Mean R-phase voltage (V, 1 dp), if reported.")
    readings: int = Field(description="Number of portal readings in the range.")
    gaps: int = Field(description="Number of missing intervals inside the range.")
    resets: int = Field(description="Number of intervals with a register reset.")
    first_at: datetime | None = Field(description="Time of the first reading; null when empty.")
    last_at: datetime | None = Field(description="Time of the last reading; null when empty.")


class ReadingSeriesResponse(BaseModel):
    """Clean consumption series for one meter."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "meter_id": "J100000",
                "resolution": "raw",
                "interval_minutes": 30,
                "interval_kind": "half_hourly",
                "points": [
                    {
                        "at": "2026-06-24T00:00:00+05:30",
                        "interval_start": "2026-06-23T23:30:00+05:30",
                        "kwh_register": 48439.16,
                        "kvah_register": 52314.29,
                        "voltage_r": 229.0,
                        "kwh": 0.42,
                        "kvah": 0.45,
                        "power_factor": 0.933,
                        "flags": [],
                    }
                ],
                "buckets": None,
                "summary": {
                    "total_kwh": 142.05,
                    "total_kvah": 153.41,
                    "avg_voltage": 229.8,
                    "readings": 337,
                    "gaps": 0,
                    "resets": 0,
                    "first_at": "2026-06-23T23:30:00+05:30",
                    "last_at": "2026-06-30T23:30:00+05:30",
                },
                "meta": {
                    "source": "portal",
                    "fetched_at": "2026-11-04T12:00:00Z",
                    "stale": False,
                },
            }
        }
    )

    meter_id: str = Field(description="Portal meter id, J followed by six digits.")
    resolution: Resolution = Field(description="Resolution of this series: raw, hourly or daily.")
    interval_minutes: int | None = Field(
        description="Detected reading cadence in minutes (median gap); null under two readings."
    )
    interval_kind: IntervalKind = Field(description="Cadence class of the meter.")
    points: list[ReadingPoint] | None = Field(
        description="Interval points when resolution is raw; null otherwise."
    )
    buckets: list[ReadingBucket] | None = Field(
        description="Hourly or daily buckets when resolution is not raw; null otherwise."
    )
    summary: ReadingSummaryOut = Field(description="Totals and data-quality counts.")
    meta: MetaOut = Field(description="Provenance and freshness of this answer.")


def _point(p: IntervalPoint) -> ReadingPoint:
    return ReadingPoint(
        at=p.at,
        interval_start=p.start,
        kwh_register=p.kwh_register,
        kvah_register=p.kvah_register,
        voltage_r=p.voltage_r,
        kwh=p.kwh,
        kvah=p.kvah,
        power_factor=p.power_factor,
        flags=list(p.flags),
    )


def _bucket(b: Bucket) -> ReadingBucket:
    return ReadingBucket(
        start=b.start,
        end=b.end,
        kwh=b.kwh,
        kvah=b.kvah,
        power_factor=b.power_factor,
        avg_voltage=b.avg_voltage,
        readings=b.readings,
        flags=list(b.flags),
    )


def _summary(s: ReadingSummary) -> ReadingSummaryOut:
    return ReadingSummaryOut(
        total_kwh=s.total_kwh,
        total_kvah=s.total_kvah,
        avg_voltage=s.avg_voltage,
        readings=s.readings,
        gaps=s.gaps,
        resets=s.resets,
        first_at=s.first_at,
        last_at=s.last_at,
    )


def to_reading_series(result: ReadingSeriesResult) -> ReadingSeriesResponse:
    return ReadingSeriesResponse(
        meter_id=result.meter_id,
        resolution=result.resolution,
        interval_minutes=result.interval_minutes,
        interval_kind=result.interval_kind,
        points=None if result.points is None else [_point(p) for p in result.points],
        buckets=None if result.buckets is None else [_bucket(b) for b in result.buckets],
        summary=_summary(result.summary),
        meta=MetaOut(
            source=result.meta.source,
            fetched_at=result.meta.fetched_at,
            stale=result.meta.stale,
        ),
    )
