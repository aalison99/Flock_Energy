from datetime import datetime, timedelta, timezone

import pytest

from app.domain.models import Reading
from app.services.readings.series import detect_interval, missing_intervals, to_interval_points

IST = timezone(timedelta(hours=5, minutes=30))
T0 = datetime(2026, 6, 24, 0, 0, tzinfo=IST)


def r(minutes: int, kwh: float, kvah: float, volt: float | None = 230.0) -> Reading:
    return Reading(T0 + timedelta(minutes=minutes), kwh, kvah, volt)


def test_deltas_and_first_point() -> None:
    pts = to_interval_points([r(0, 100.0, 110.0), r(30, 100.42, 110.46)], 30)
    assert pts[0].start is None and pts[0].kwh is None and pts[0].flags == ()
    assert pts[1].start == T0
    assert pts[1].kwh == 0.42  # 100.42 - 100.00
    assert pts[1].kvah == 0.46  # 110.46 - 110.00
    assert pts[1].power_factor == 0.913  # 0.42 / 0.46 = 0.91304


def test_reset_on_kwh() -> None:
    pts = to_interval_points([r(0, 100.0, 110.0), r(30, 5.0, 111.0)], 30)
    p = pts[1]
    assert (p.kwh, p.kvah, p.power_factor) == (None, None, None)
    assert p.flags == ("register_reset",)


def test_reset_on_kvah() -> None:
    pts = to_interval_points([r(0, 100.0, 110.0), r(30, 101.0, 3.0)], 30)
    assert (pts[1].kwh, pts[1].kvah, pts[1].power_factor) == (None, None, None)
    assert pts[1].flags == ("register_reset",)


def test_pf_none_when_kvah_zero() -> None:
    pts = to_interval_points([r(0, 100.0, 110.0), r(30, 100.5, 110.0)], 30)
    assert pts[1].kwh == 0.5 and pts[1].kvah == 0.0
    assert pts[1].power_factor is None
    assert pts[1].flags == ()


def test_pf_above_one_flagged_but_returned() -> None:
    pts = to_interval_points([r(0, 100.0, 110.0), r(30, 100.6, 110.5)], 30)
    assert pts[1].power_factor == 1.2  # 0.6 / 0.5
    assert pts[1].flags == ("pf_out_of_range",)


def test_rounding_removes_float_noise() -> None:
    pts = to_interval_points([r(0, 48438.74, 52313.84), r(30, 48439.16, 52314.29)], 30)
    assert pts[1].kwh == 0.42
    assert pts[1].kvah == 0.45


def test_detect_interval() -> None:
    assert detect_interval([r(0, 1, 1), r(30, 2, 2), r(60, 3, 3)]) == 30
    assert detect_interval([r(0, 1, 1), r(1440, 2, 2), r(2880, 3, 3)]) == 1440
    assert detect_interval([r(0, 1, 1), r(45, 2, 2), r(90, 3, 3)]) == 45
    assert detect_interval([r(0, 1, 1)]) is None
    assert detect_interval([]) is None


def test_detect_interval_is_median_so_a_gap_does_not_skew() -> None:
    # diffs 30, 30, 90 -> median 30
    assert detect_interval([r(0, 1, 1), r(30, 2, 2), r(60, 3, 3), r(150, 4, 4)]) == 30


def test_gap_flag_on_reading_at_end_of_long_interval() -> None:
    pts = to_interval_points([r(0, 1.0, 1.0), r(30, 2.0, 2.0), r(120, 5.0, 5.0)], 30)
    assert pts[1].flags == ()
    assert pts[2].flags == ("gap",)
    assert pts[2].kwh == 3.0  # still reported over the longer span


def test_unsorted_input_is_sorted() -> None:
    pts = to_interval_points([r(30, 2.0, 2.0), r(0, 1.0, 1.0)], 30)
    assert [p.at for p in pts] == [T0, T0 + timedelta(minutes=30)]
    assert pts[1].kwh == 1.0


def test_duplicate_timestamp_dropped_keeping_first() -> None:
    pts = to_interval_points([r(0, 1.0, 1.0), r(30, 2.0, 2.0), r(30, 9.0, 9.0)], 30)
    assert len(pts) == 2
    assert pts[1].kwh_register == 2.0


def test_empty() -> None:
    assert to_interval_points([], None) == []


@pytest.mark.parametrize(
    ("span", "missing"), [(30, 0), (40, 1), (45, 1), (60, 1), (75, 2), (90, 2), (91, 3)]
)
def test_gap_threshold_and_missing_count(span: int, missing: int) -> None:
    assert missing_intervals(span, 30) == missing
    pts = to_interval_points([r(0, 1.0, 1.0), r(span, 2.0, 2.0)], 30)
    assert pts[1].flags == (("gap",) if missing else ())


def test_missing_intervals_unknown_interval() -> None:
    assert missing_intervals(100, None) == 0


def test_detect_interval_rounds_half_up() -> None:
    # diffs 30, 31 -> median 30.5 -> 31 (not truncated to 30)
    assert detect_interval([r(0, 1, 1), r(30, 2, 2), r(61, 3, 3)]) == 31
