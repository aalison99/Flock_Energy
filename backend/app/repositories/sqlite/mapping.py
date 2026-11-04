"""Pure row <-> domain conversions for every table (no I/O).

Conventions: stored timestamps are ISO 8601 text. `synced_at` and sync-run times are UTC;
reading instants are normalised to IST (+05:30) so text order equals time order and the
IST calendar-day range filter is a plain string comparison.
"""

import json
from collections.abc import Mapping
from datetime import UTC, date, datetime, time, timedelta, timezone
from typing import Any

from app.domain.models import (
    HIERARCHY_LEVELS,
    GeoPoint,
    HierarchyPath,
    InstallStatus,
    InstallType,
    Meter,
    NodeRef,
    PhaseType,
    Reading,
    SyncRun,
    SyncStatus,
    SyncStrategy,
    Transformer,
)

IST = timezone(timedelta(hours=5, minutes=30))

Row = Mapping[Any, Any]  # a SQLAlchemy RowMapping or a plain dict


def utc_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def ist_text(value: datetime) -> str:
    return value.astimezone(IST).isoformat()


def _parse(text: str) -> datetime:
    return datetime.fromisoformat(text)


def parse_time(text: str) -> datetime:
    """Read back a stored timestamp (UTC for `synced_at`)."""
    return _parse(text)


# --- meters -----------------------------------------------------------------------------------


def _code_column(level: str) -> str:
    return "dt_node_code" if level == "dt" else f"{level}_code"


def meter_to_row(meter: Meter, synced_at: datetime) -> dict[str, Any]:
    """Flatten a Meter. `dt_code` is the meter's own field; the dt level code is `dt_node_code`."""
    row: dict[str, Any] = {
        "meter_id": meter.meter_id,
        "serial_no": meter.serial_no,
        "make": meter.make,
        "phase_type": meter.phase_type.value,
        "install_status": meter.install_status.value,
        "install_type": meter.install_type.value if meter.install_type else None,
        "build": meter.build,
        "dt_code": meter.dt_code,
        "has_hierarchy": meter.hierarchy is not None,
        "lat": meter.geo.lat if meter.geo else None,
        "lng": meter.geo.lng if meter.geo else None,
        "synced_at": utc_text(synced_at),
    }
    for level in HIERARCHY_LEVELS:
        node = meter.hierarchy.get(level) if meter.hierarchy else None
        row[_code_column(level.value)] = node.code if node else None
        row[f"{level.value}_name"] = node.name if node else None
    return row


def row_to_meter(row: Row) -> Meter:
    hierarchy: HierarchyPath | None = None
    if row["has_hierarchy"]:
        nodes = {
            level.value: NodeRef(row[_code_column(level.value)], row[f"{level.value}_name"])
            for level in HIERARCHY_LEVELS
        }
        hierarchy = HierarchyPath(**nodes)
    geo = GeoPoint(row["lat"], row["lng"]) if row["lat"] is not None else None
    return Meter(
        meter_id=row["meter_id"],
        serial_no=row["serial_no"],
        make=row["make"],
        phase_type=PhaseType(row["phase_type"]),
        install_status=InstallStatus(row["install_status"]),
        install_type=InstallType(row["install_type"]) if row["install_type"] else None,
        build=row["build"],
        dt_code=row["dt_code"],
        hierarchy=hierarchy,
        geo=geo,
    )


# --- transformers -----------------------------------------------------------------------------


def transformer_to_row(t: Transformer, synced_at: datetime) -> dict[str, Any]:
    return {
        "code": t.code,
        "name": t.name,
        "feeder_code": t.feeder_code,
        "capacity_kva": t.capacity_kva,
        "synced_at": utc_text(synced_at),
    }


def row_to_transformer(row: Row) -> Transformer:
    return Transformer(row["code"], row["name"], row["feeder_code"], row["capacity_kva"])


# --- readings ---------------------------------------------------------------------------------


def reading_to_row(meter_id: str, r: Reading) -> dict[str, Any]:
    return {
        "meter_id": meter_id,
        "at": ist_text(r.at),
        "kwh_register": r.kwh_register,
        "kvah_register": r.kvah_register,
        "voltage_r": r.voltage_r,
    }


def row_to_reading(row: Row) -> Reading:
    return Reading(_parse(row["at"]), row["kwh_register"], row["kvah_register"], row["voltage_r"])


def ist_day_bounds(start: date | None, end: date | None) -> tuple[str | None, str | None]:
    """Text bounds [lo, hi) for inclusive IST calendar days; None means unbounded."""
    lo = ist_text(datetime.combine(start, time(), IST)) if start else None
    hi = ist_text(datetime.combine(end + timedelta(days=1), time(), IST)) if end else None
    return lo, hi


# --- sync runs --------------------------------------------------------------------------------


def counts_to_json(counts: Mapping[str, int]) -> str:
    return json.dumps(dict(counts), sort_keys=True)


def row_to_sync_run(row: Row) -> SyncRun:
    return SyncRun(
        id=row["id"],
        status=SyncStatus(row["status"]),
        strategy=SyncStrategy(row["strategy"]) if row["strategy"] else None,
        started_at=_parse(row["started_at"]),
        finished_at=_parse(row["finished_at"]) if row["finished_at"] else None,
        counts=json.loads(row["counts"]),
        error=row["error"],
    )
