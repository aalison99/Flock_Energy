"""Each anomaly rule: positive, negative and boundary cases on hand-made readings."""

import pytest

from app.domain.models import InstallStatus, Reading
from app.services.analytics.anomalies.models import AnomalyThresholds
from app.services.analytics.anomalies.registry import RULE_CLASSES, build_rules
from app.services.analytics.anomalies.rules import (
    ConsumptionSpike,
    DataGap,
    Flatline,
    InactiveButConsuming,
    RegisterReset,
    VoltageOutOfBand,
)
from app.services.quality.models import Severity
from tests.support.readings_factory import at, profile, series

TH = AnomalyThresholds(
    voltage_min_v=207.0,
    voltage_max_v=253.0,
    flatline_hours=6.0,
    spike_sigma=4.0,
    spike_min_points=24,
    inactive_min_kwh=0.5,
)


def test_registry_order_and_ids() -> None:
    rules = build_rules(TH)
    assert [r.id for r in rules] == [
        "inactive_but_consuming",
        "voltage_out_of_band",
        "flatline",
        "register_reset",
        "data_gap",
        "consumption_spike",
    ]
    assert len(RULE_CLASSES) == len(rules)
    assert [r.severity for r in rules] == [
        Severity.ERROR,
        Severity.WARNING,
        Severity.WARNING,
        Severity.WARNING,
        Severity.INFO,
        Severity.WARNING,
    ]
    assert all(r.description for r in rules)


# --- inactive_but_consuming -------------------------------------------------------------------


@pytest.mark.parametrize("status", [InstallStatus.FAULTY, InstallStatus.DECOMMISSIONED])
def test_inactive_but_consuming_fires(status: InstallStatus) -> None:
    p = profile(series([0.3, 0.3]), status=status)  # 0.6 kWh > 0.5
    [a] = InactiveButConsuming(TH).evaluate(p)
    assert (a.rule, a.severity, a.meter_id, a.at) == (
        "inactive_but_consuming",
        Severity.ERROR,
        "J1",
        None,
    )
    assert a.evidence == {"install_status": status.value, "total_kwh": 0.6}


def test_inactive_but_consuming_boundary_exactly_threshold_does_not_fire() -> None:
    p = profile(series([0.25, 0.25]), status=InstallStatus.FAULTY)  # exactly 0.5
    assert InactiveButConsuming(TH).evaluate(p) == []


def test_inactive_but_consuming_ignores_installed_and_unknown() -> None:
    for status in (InstallStatus.INSTALLED, InstallStatus.UNKNOWN):
        assert InactiveButConsuming(TH).evaluate(profile(series([5.0]), status=status)) == []


def test_inactive_but_consuming_ignores_quiet_inactive_meter() -> None:
    assert (
        InactiveButConsuming(TH).evaluate(
            profile(series([0.0, 0.0]), status=InstallStatus.DECOMMISSIONED)
        )
        == []
    )


# --- voltage_out_of_band ----------------------------------------------------------------------


def test_voltage_one_anomaly_per_contiguous_run() -> None:
    # readings 0..7: runs at 1-2 (low, high) and 5 (low); 3,4 in band
    volts = [230, 200.0, 260.0, 230, 230, 150.0, 230, 230]
    p = profile(series([1.0] * 7, voltages=volts))
    found = VoltageOutOfBand(TH).evaluate(p)
    assert len(found) == 2
    first, second = found
    assert first.at == at(30)
    assert first.evidence == {
        "first_at": at(30).isoformat(),
        "last_at": at(60).isoformat(),
        "min_v": 200.0,
        "max_v": 260.0,
        "count": 2,
    }
    assert second.evidence["count"] == 1 and second.evidence["min_v"] == 150.0
    assert first.severity is Severity.WARNING


def test_voltage_boundaries_inclusive_band_does_not_fire() -> None:
    p = profile(series([1.0, 1.0, 1.0], voltages=[207.0, 253.0, 230.0, 230.0]))
    assert VoltageOutOfBand(TH).evaluate(p) == []


def test_voltage_just_outside_fires_and_none_breaks_a_run() -> None:
    volts: list[float | None] = [230.0, 206.9, None, 253.1, 230.0]
    found = VoltageOutOfBand(TH).evaluate(profile(series([1.0] * 4, voltages=volts)))
    assert [a.evidence["count"] for a in found] == [1, 1]


# --- flatline ---------------------------------------------------------------------------------


def test_flatline_exactly_threshold_fires() -> None:
    # 12 zero half-hour intervals = 6.0 h exactly
    p = profile(series([1.0] + [0.0] * 12 + [1.0]))
    [a] = Flatline(TH).evaluate(p)
    assert a.evidence == {
        "start": at(30).isoformat(),
        "end": at(30 + 360).isoformat(),
        "hours": 6.0,
    }
    assert a.at == at(30) and a.severity is Severity.WARNING


def test_flatline_just_below_threshold_does_not_fire() -> None:
    assert Flatline(TH).evaluate(profile(series([1.0] + [0.0] * 11 + [1.0]))) == []


def test_flatline_one_per_span_and_nonzero_breaks_span() -> None:
    steps = [0.0] * 12 + [0.5] + [0.0] * 14 + [1.0]
    found = Flatline(TH).evaluate(profile(series(steps)))
    assert [a.evidence["hours"] for a in found] == [6.0, 7.0]


def test_flatline_daily_zero_day_counts_24h() -> None:
    p = profile(series([5.0, 0.0, 5.0], step_min=1440))
    [a] = Flatline(TH).evaluate(p)
    assert a.evidence["hours"] == 24.0


@pytest.mark.parametrize(
    "status", [InstallStatus.FAULTY, InstallStatus.DECOMMISSIONED, InstallStatus.UNKNOWN]
)
def test_flatline_ignores_non_installed_meters(status: InstallStatus) -> None:
    p = profile(series([0.0] * 20), status=status)
    assert Flatline(TH).evaluate(p) == []


def test_flatline_reset_interval_breaks_span() -> None:
    # 8 zero + reset (kwh None) + 8 zero: neither side reaches 6 h... 4 h each
    p = profile(series([0.0] * 8 + [-100.0] + [0.0] * 8))
    assert Flatline(TH).evaluate(p) == []


# --- register_reset ---------------------------------------------------------------------------


def test_register_reset_fires_per_reset() -> None:
    p = profile(series([1.0, -90.0, 1.0, -5.0, 1.0]))
    found = RegisterReset(TH).evaluate(p)
    assert [a.at for a in found] == [at(60), at(120)]
    assert found[0].evidence["previous_kwh_register"] == 101.0
    assert found[0].evidence["kwh_register"] == 11.0
    assert found[0].severity is Severity.WARNING


def test_register_reset_negative_case() -> None:
    assert RegisterReset(TH).evaluate(profile(series([1.0, 0.0, 2.0]))) == []


# --- data_gap ---------------------------------------------------------------------------------


def test_data_gap_reports_missing_count() -> None:
    # readings every 30 min; drop 150 and 180 => a 120-minute hole between 120 and 210,
    # ceil(120 / 30) - 1 = ... span is 90 min (120 -> 210) => 2 missing
    gapped = [r for r in series([1.0] * 10) if r.at not in (at(150), at(180))]
    [a] = DataGap(TH).evaluate(profile(gapped))
    assert a.evidence["missing"] == 2
    assert a.at == at(210) and a.severity is Severity.INFO


def test_data_gap_negative() -> None:
    assert DataGap(TH).evaluate(profile(series([1.0] * 10))) == []


# --- consumption_spike ------------------------------------------------------------------------


def _spiky(n: int, spike: float) -> list[Reading]:
    return series([1.0] * (n - 1) + [spike])


def test_spike_fires_for_an_outlier_interval() -> None:
    # 29 values of 1.0 and one of 100: mean 4.3, pstdev ~17.7; threshold ~75.1 < 100
    p = profile(_spiky(30, 100.0))
    [a] = ConsumptionSpike(TH).evaluate(p)
    assert a.evidence["kwh"] == 100.0
    assert a.at == at(30 * 30)
    assert a.severity is Severity.WARNING


def test_spike_needs_min_points() -> None:
    # 23 intervals only (24 readings): below spike_min_points=24 intervals
    assert ConsumptionSpike(TH).evaluate(profile(_spiky(23, 1000.0))) == []


def test_spike_exactly_min_points_is_evaluated() -> None:
    assert len(ConsumptionSpike(TH).evaluate(profile(_spiky(24, 1000.0)))) == 1


def test_spike_zero_stdev_never_fires() -> None:
    assert ConsumptionSpike(TH).evaluate(profile(series([1.0] * 40))) == []


def test_spike_boundary_exactly_at_threshold_does_not_fire() -> None:
    # 12 intervals of 0 and 12 of 2.0: mean 1.0, population stdev 1.0 (exact in floats)
    p = profile(series([0.0, 2.0] * 12))
    at_limit = AnomalyThresholds(207.0, 253.0, 6.0, 1.0, 24, 0.5)  # threshold 2.0 == the value
    assert ConsumptionSpike(at_limit).evaluate(p) == []
    below = AnomalyThresholds(207.0, 253.0, 6.0, 0.99, 24, 0.5)  # threshold 1.99 < 2.0
    assert len(ConsumptionSpike(below).evaluate(p)) == 12


def test_spike_ignores_gap_intervals() -> None:
    # 30 steps of 1.0 with readings 10 and 11 missing: one gap interval holds 3.0 kWh. Counted
    # as a candidate it would exceed mean + 4 sigma; ignored, the series is constant.
    gapped = [r for r in series([1.0] * 30) if r.at not in (at(300), at(330))]
    assert ConsumptionSpike(TH).evaluate(profile(gapped)) == []


def test_all_rules_quiet_on_empty_profile() -> None:
    p = profile([])
    assert [r.evaluate(p) for r in build_rules(TH)] == [[]] * 6
