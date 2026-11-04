from datetime import datetime, timedelta, timezone

from app.services.readings.buckets import BUCKETERS, Resolution, aggregate
from app.services.readings.series import IntervalPoint

IST = timezone(timedelta(hours=5, minutes=30))


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 6, day, hour, minute, tzinfo=IST)


def pt(
    end: datetime,
    mins: int,
    kwh: float | None,
    kvah: float | None,
    volt: float | None = 230.0,
    flags: tuple[str, ...] = (),
) -> IntervalPoint:
    pf = round(kwh / kvah, 3) if kwh is not None and kvah else None
    return IntervalPoint(end, end - timedelta(minutes=mins), 0.0, 0.0, volt, kwh, kvah, pf, flags)


def first(end: datetime) -> IntervalPoint:
    return IntervalPoint(end, None, 0.0, 0.0, 230.0, None, None, None, ())


def test_registry_has_no_raw() -> None:
    assert set(BUCKETERS) == {Resolution.HOURLY, Resolution.DAILY}


def test_hourly_sums_two_half_hours() -> None:
    pts = [
        first(at(24, 0)),
        pt(at(24, 0, 30), 30, 0.4, 0.5, 220.0),
        pt(at(24, 1), 30, 0.2, 0.25, 231.0),
        pt(at(24, 1, 30), 30, 0.3, 0.4, 230.0),
    ]
    b = aggregate(pts, Resolution.HOURLY)
    assert len(b) == 2
    # intervals starting 00:00 and 00:30 -> hour 00:00; their ends are 00:30 and 01:00
    assert (b[0].start, b[0].end) == (at(24, 0), at(24, 1))
    assert b[0].kwh == 0.6  # 0.4 + 0.2
    assert b[0].kvah == 0.75  # 0.5 + 0.25
    assert b[0].power_factor == 0.8  # 0.6 / 0.75
    assert b[0].avg_voltage == 225.5  # (220 + 231) / 2
    assert b[0].readings == 2
    assert b[1].start == at(24, 1) and b[1].kwh == 0.3 and b[1].readings == 1


def test_attribution_by_interval_start_across_midnight() -> None:
    pts = [
        first(at(24, 23)),
        pt(at(24, 23, 30), 30, 1.0, 1.0),
        pt(at(25, 0), 30, 2.0, 2.0),  # 23:30 -> 00:00 belongs to 24/06
        pt(at(25, 0, 30), 30, 4.0, 4.0),  # belongs to 25/06
    ]
    b = aggregate(pts, Resolution.DAILY)
    assert [(x.start, x.kwh) for x in b] == [(at(24, 0), 3.0), (at(25, 0), 4.0)]
    assert b[0].end == at(25, 0)


def test_daily_meter_one_bucket_per_day() -> None:
    pts = [
        first(at(23, 0)),
        pt(at(24, 0), 1440, 21.32, 23.02),
        pt(at(25, 0), 1440, 21.32, 23.03),
    ]
    b = aggregate(pts, Resolution.DAILY)
    assert [(x.start, x.kwh) for x in b] == [(at(23, 0), 21.32), (at(24, 0), 21.32)]


def test_none_deltas_skipped_and_all_none_gives_none() -> None:
    pts = [
        first(at(24, 0)),
        pt(at(24, 0, 30), 30, None, None, flags=("register_reset",)),
        pt(at(24, 1), 30, 0.5, 0.5),
        pt(at(24, 1, 30), 30, None, None, flags=("register_reset",)),
    ]
    b = aggregate(pts, Resolution.HOURLY)
    assert b[0].kwh == 0.5 and b[0].flags == ("register_reset",)
    assert b[1].kwh is None and b[1].kvah is None and b[1].power_factor is None


def test_flags_union_sorted() -> None:
    pts = [
        first(at(24, 0)),
        pt(at(24, 0, 30), 30, 1.0, 0.5, flags=("pf_out_of_range",)),
        pt(at(24, 1), 30, 1.0, 1.0, flags=("gap",)),
    ]
    assert aggregate(pts, Resolution.HOURLY)[0].flags == ("gap", "pf_out_of_range")


def test_avg_voltage_ignores_none() -> None:
    pts = [
        first(at(24, 0)),
        pt(at(24, 0, 30), 30, 1.0, 1.0, None),
        pt(at(24, 1), 30, 1.0, 1.0, 230.0),
    ]
    assert aggregate(pts, Resolution.HOURLY)[0].avg_voltage == 230.0


def test_empty_and_first_only() -> None:
    assert aggregate([], Resolution.DAILY) == []
    assert aggregate([first(at(24, 0))], Resolution.DAILY) == []


def test_avg_voltage_one_decimal() -> None:
    pts = [
        first(at(24, 0)),
        pt(at(24, 0, 20), 20, 1.0, 1.0, 229.0),
        pt(at(24, 0, 40), 20, 1.0, 1.0, 230.0),
        pt(at(24, 1), 20, 1.0, 1.0, 230.5),
    ]
    assert aggregate(pts, Resolution.HOURLY)[0].avg_voltage == 229.8  # 689.5 / 3 = 229.833


def test_gap_across_midnight_flags_bucket_of_interval_start() -> None:
    pts = [
        first(at(24, 22, 30)),
        pt(at(25, 2), 210, 5.0, 5.0, flags=("gap",)),  # 22:30 -> 02:00
        pt(at(25, 2, 30), 30, 1.0, 1.0),
    ]
    b = aggregate(pts, Resolution.DAILY)
    assert [(x.start, x.kwh, x.flags) for x in b] == [
        (at(24, 0), 5.0, ("gap",)),
        (at(25, 0), 1.0, ()),
    ]


def test_bucket_pf_above_one_is_flagged_even_if_no_member_is() -> None:
    pts = [
        first(at(24, 0)),
        pt(at(24, 0, 30), 30, 0.5, 0.0),  # kvah 0 -> member PF None, no flag
        pt(at(24, 1), 30, 0.5, 0.4),  # helper adds no flags, so no member carries one
    ]
    b = aggregate(pts, Resolution.HOURLY)[0]
    assert b.power_factor == 2.5  # 1.0 / 0.4
    assert b.flags == ("pf_out_of_range",)
