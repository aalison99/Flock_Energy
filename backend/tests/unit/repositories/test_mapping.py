from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.domain.models import (
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
from app.repositories.sqlite import mapping

IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)


def _path(blank: bool = False) -> HierarchyPath:
    def ref(n: str) -> NodeRef:
        return NodeRef(None, f"{n} name") if blank else NodeRef(f"{n}-1", f"{n} name")

    return HierarchyPath(
        zone=ref("z"),
        circle=ref("c"),
        division=ref("d"),
        subdivision=ref("s"),
        substation=ref("ss"),
        feeder=ref("f"),
        dt=NodeRef("DT9", None),
    )


def _meter(**over: object) -> Meter:
    base: dict[str, object] = {
        "meter_id": "J1",
        "serial_no": "S1",
        "make": "Acme",
        "phase_type": PhaseType.THREE,
        "install_status": InstallStatus.FAULTY,
        "install_type": InstallType.CT_OPERATED,
        "build": "v2",
        "dt_code": "DT9",
        "hierarchy": _path(),
        "geo": GeoPoint(12.5, 77.25),
    }
    return Meter(**{**base, **over})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "meter",
    [
        _meter(),
        _meter(hierarchy=_path(blank=True)),
        _meter(hierarchy=None, geo=None, install_type=None, build=None),
        _meter(hierarchy=None, dt_code=None),
        _meter(geo=GeoPoint(-90.0, 180.0)),
        _meter(dt_code="OTHER"),  # meter-level dt_code differs from hierarchy dt code
        _meter(dt_code=None),
        _meter(dt_code="DT9", hierarchy=replace(_path(), dt=NodeRef(None, "dt name"))),
    ],
)
def test_meter_round_trip(meter: Meter) -> None:
    row = mapping.meter_to_row(meter, NOW)
    assert mapping.row_to_meter(row) == meter


def test_meter_row_columns() -> None:
    row = mapping.meter_to_row(_meter(), NOW)
    assert row["phase_type"] == "three"
    assert row["has_hierarchy"] is True
    assert row["zone_code"] == "z-1"
    assert row["dt_name"] is None
    assert row["dt_node_code"] == "DT9"
    assert row["lat"] == 12.5
    assert row["synced_at"] == "2026-07-01T12:00:00+00:00"


def test_meter_without_hierarchy_row() -> None:
    row = mapping.meter_to_row(_meter(hierarchy=None, geo=None), NOW)
    assert row["has_hierarchy"] is False
    assert row["zone_code"] is None
    assert row["lat"] is None and row["lng"] is None
    assert row["dt_code"] == "DT9"


def test_synced_at_is_normalised_to_utc() -> None:
    row = mapping.meter_to_row(_meter(), datetime(2026, 7, 1, 17, 30, tzinfo=IST))
    assert row["synced_at"] == "2026-07-01T12:00:00+00:00"


def test_dt_code_and_dt_node_code_are_independent_columns() -> None:
    row = mapping.meter_to_row(_meter(dt_code="OTHER"), NOW)
    assert (row["dt_code"], row["dt_node_code"]) == ("OTHER", "DT9")


def test_transformer_round_trip() -> None:
    for t in (Transformer("DT1", "Name", "F1", 100), Transformer("DT2", "N", None, 5)):
        row = mapping.transformer_to_row(t, NOW)
        assert row["synced_at"] == "2026-07-01T12:00:00+00:00"
        assert mapping.row_to_transformer(row) == t


def test_reading_round_trip_keeps_ist_offset() -> None:
    r = Reading(datetime(2026, 6, 24, 0, 0, tzinfo=IST), 1.5, 2.5, None)
    row = mapping.reading_to_row("J1", r)
    assert row["at"] == "2026-06-24T00:00:00+05:30"
    back = mapping.row_to_reading(row)
    assert back == r
    assert back.at.utcoffset() == timedelta(hours=5, minutes=30)


def test_reading_in_other_zone_is_stored_as_ist() -> None:
    r = Reading(datetime(2026, 6, 23, 18, 30, tzinfo=UTC), 1.0, 1.0, 230.0)
    row = mapping.reading_to_row("J1", r)
    assert row["at"] == "2026-06-24T00:00:00+05:30"
    assert mapping.row_to_reading(row) == r


def test_ist_day_bounds() -> None:
    from datetime import date

    lo, hi = mapping.ist_day_bounds(date(2026, 6, 24), date(2026, 6, 25))
    assert lo == "2026-06-24T00:00:00+05:30"
    assert hi == "2026-06-26T00:00:00+05:30"
    assert mapping.ist_day_bounds(None, None) == (None, None)


def test_sync_run_round_trip() -> None:
    row = {
        "id": 3,
        "status": "succeeded",
        "strategy": "crawl",
        "started_at": "2026-07-01T12:00:00+00:00",
        "finished_at": "2026-07-01T12:05:00+00:00",
        "counts": '{"meters": 4}',
        "error": None,
    }
    run = mapping.row_to_sync_run(row)
    assert run == SyncRun(
        3,
        SyncStatus.SUCCEEDED,
        SyncStrategy.CRAWL,
        NOW,
        NOW + timedelta(minutes=5),
        {"meters": 4},
        None,
    )


def test_sync_run_running_row() -> None:
    row = {
        "id": 1,
        "status": "running",
        "strategy": None,
        "started_at": "2026-07-01T12:00:00+00:00",
        "finished_at": None,
        "counts": "{}",
        "error": None,
    }
    run = mapping.row_to_sync_run(row)
    assert run.strategy is None and run.finished_at is None and dict(run.counts) == {}


def test_counts_json_is_stable() -> None:
    assert mapping.counts_to_json({"b": 1, "a": 2}) == '{"a": 2, "b": 1}'
