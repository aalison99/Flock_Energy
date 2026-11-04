from app.domain.models import Reading
from app.services.analytics.profile import profile_meter
from tests.support.readings_factory import T0, at, meter, series


def test_half_hourly_profile() -> None:
    # steps 1.0 + 2.0 + 0.5 = 3.5 kWh; kVAh = 1.25 x kWh => 4.375
    p = profile_meter(meter(), series([1.0, 2.0, 0.5]))
    assert p.interval_minutes == 30
    assert p.interval_kind == "half_hourly"
    assert p.total_kwh == 3.5
    assert p.total_kvah == 4.375
    assert (p.first_at, p.last_at) == (T0, at(90))
    assert len(p.points) == 4
    assert p.reporting is True


def test_daily_profile() -> None:
    p = profile_meter(meter(), series([10.0, 12.0], step_min=1440))
    assert (p.interval_minutes, p.interval_kind) == (1440, "daily")
    assert p.total_kwh == 22.0


def test_negative_delta_is_excluded_from_totals() -> None:
    # +1, then a reset (-50, excluded), then +2 => 3.0
    p = profile_meter(meter(), series([1.0, -50.0, 2.0]))
    assert p.total_kwh == 3.0


def test_silent_meter_with_no_readings() -> None:
    p = profile_meter(meter(), [])
    assert p.points == [] and p.interval_minutes is None and p.interval_kind == "unknown"
    assert (p.total_kwh, p.total_kvah, p.first_at, p.last_at) == (0.0, 0.0, None, None)
    assert p.reporting is False


def test_single_reading_is_silent() -> None:
    p = profile_meter(meter(), [Reading(T0, 5.0, 6.0, 230.0)])
    assert p.reporting is False
    assert p.total_kwh == 0.0
    assert p.first_at == p.last_at == T0
