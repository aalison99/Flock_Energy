"""AnalyticsService over hand-made readings and fake repositories.

Fleet used throughout (all readings start at 2026-06-01 00:00 IST, kVAh = 1.25 x kWh):
  J1  installed, DT-001/F-001, half-hourly, 4 steps of 1.0   -> 4.0 kWh, 5.0 kVAh
  J2  installed, DT-001/F-001, half-hourly, 4 steps of 2.0   -> 8.0 kWh, 10.0 kVAh
  J3  installed, DT-002/F-002, daily, steps 10, 20            -> 30.0 kWh, 37.5 kVAh
  J4  decommissioned, DT-002/F-002, half-hourly, 4 x 1.0      -> 4.0 kWh, 5.0 kVAh
  J5  installed, DT-001/F-001, no readings (silent)
"""

from datetime import timedelta

import pytest

from app.domain.exceptions import IndexNotReadyError, NotFoundError, ValidationError
from app.domain.models import InstallStatus, Reading, Transformer
from app.services.analytics.anomalies.models import Anomaly, AnomalyThresholds
from app.services.analytics.anomalies.registry import build_rules
from app.services.analytics.profile import MeterProfile
from app.services.analytics_service import AnalyticsService
from app.services.quality.models import Severity
from app.services.readings.buckets import Resolution
from tests.support.fakes import (
    FakeMeterRepository,
    FakeReadingRepository,
    FakeTransformerRepository,
)
from tests.support.hierarchy_factory import make_meter, make_transformer
from tests.support.readings_factory import IST, T0, at, series

pytestmark = pytest.mark.anyio

TH = AnomalyThresholds(207.0, 253.0, 6.0, 4.0, 24, 0.5)
DT1 = "Z-01/C-01/D-01/SD-01/SS-01/F-001/DT-001"
DT2 = "Z-01/C-01/D-01/SD-01/SS-01/F-002/DT-002"
F2 = {"feeder": ("F-002", "Feeder 2"), "dt": ("DT-002", "DT 2")}


def _fleet() -> tuple[FakeMeterRepository, FakeTransformerRepository, FakeReadingRepository]:
    meters = [
        make_meter("J1"),
        make_meter("J2"),
        make_meter("J3", **F2),
        make_meter("J4", status=InstallStatus.DECOMMISSIONED, **F2),
        make_meter("J5"),
    ]
    readings = {
        "J1": series([1.0] * 4),
        "J2": series([2.0] * 4),
        "J3": series([10.0, 20.0], step_min=1440),
        "J4": series([1.0] * 4),
    }
    transformers = [make_transformer("DT-001", feeder_code="F-001")]
    return (
        FakeMeterRepository(meters),
        FakeTransformerRepository(transformers),
        FakeReadingRepository(readings),
    )


def _service(rules=None, fleet=None) -> AnalyticsService:  # type: ignore[no-untyped-def]
    meters, transformers, readings = fleet or _fleet()
    return AnalyticsService(
        meters, transformers, readings, build_rules(TH) if rules is None else rules
    )


# --- summary ----------------------------------------------------------------------------------


async def test_summary_counts() -> None:
    s = await _service().summary()
    assert s.total_meters == 5
    assert s.meters_by_status == {
        "installed": 4,
        "faulty": 0,
        "decommissioned": 1,
        "unknown": 0,
    }
    assert (s.reporting_meters, s.silent_meters) == (4, 1)
    assert s.total_kwh == 46.0  # 4 + 8 + 30 + 4
    assert s.first_reading_at == T0
    assert s.last_reading_at == at(2 * 1440)  # J3's last reading
    assert s.interval_kinds == {"half_hourly": 3, "daily": 1, "unknown": 1}
    assert s.anomalies_by_rule == {
        "inactive_but_consuming": 1,  # J4
        "voltage_out_of_band": 0,
        "flatline": 0,
        "register_reset": 0,
        "data_gap": 0,
        "consumption_spike": 0,
    }


async def test_every_method_needs_the_index() -> None:
    svc = _service(
        fleet=(FakeMeterRepository(), FakeTransformerRepository(), FakeReadingRepository())
    )
    for call in (
        svc.summary(),
        svc.consumption(None, Resolution.DAILY),
        svc.top_consumers(None, 10),
        svc.anomalies(None, None, None, 1, 50),
        svc.meter_anomalies("J1"),
        svc.transformer_load("utilisation", 40),
    ):
        with pytest.raises(IndexNotReadyError):
            await call


# --- consumption ------------------------------------------------------------------------------


async def test_consumption_daily_whole_fleet() -> None:
    c = await _service().consumption(None, Resolution.DAILY)
    assert (c.meters_included, c.meters_excluded_coarser) == (4, 0)
    first, second = c.items
    # June 1: J1 4 + J2 8 + J4 4 + J3 10 (its first daily interval starts June 1) = 26
    assert (first.start, first.end) == (T0, T0 + timedelta(days=1))
    assert (first.kwh, first.kvah, first.meters) == (26.0, 32.5, 4)
    # June 2: J3's second day only = 20 kWh, 25 kVAh
    assert (second.start, second.kwh, second.kvah, second.meters) == (at(1440), 20.0, 25.0, 1)


async def test_consumption_hourly_excludes_coarser_meters() -> None:
    c = await _service().consumption(None, Resolution.HOURLY)
    assert (c.meters_included, c.meters_excluded_coarser) == (3, 1)  # J3 is daily; J5 is silent
    # an hour holds two half-hour intervals starting in it
    # J1: 2 x 1.0 = 2, J2: 2 x 2.0 = 4, J4: 2 x 1.0 = 2  => 8.0 kWh per hour, 10.0 kVAh
    assert [(b.start, b.kwh, b.kvah, b.meters) for b in c.items] == [
        (T0, 8.0, 10.0, 3),
        (at(60), 8.0, 10.0, 3),
    ]


async def test_consumption_node_filter() -> None:
    c = await _service().consumption(DT1, Resolution.DAILY)
    assert c.node == DT1
    assert (c.meters_included, c.meters_excluded_coarser) == (2, 0)  # J1, J2 (J5 silent)
    assert [(b.kwh, b.meters) for b in c.items] == [(12.0, 2)]


async def test_consumption_unknown_node_and_raw() -> None:
    with pytest.raises(NotFoundError):
        await _service().consumption("Z-09", Resolution.DAILY)
    with pytest.raises(ValidationError):
        await _service().consumption(None, Resolution.RAW)


# --- top consumers ----------------------------------------------------------------------------


async def test_top_consumers_descending_ties_by_id_and_limit() -> None:
    rows = await _service().top_consumers(None, 10)
    assert [(m.meter_id, kwh) for m, kwh in rows] == [
        ("J3", 30.0),
        ("J2", 8.0),
        ("J1", 4.0),  # ties with J4 at 4.0: smaller id first
        ("J4", 4.0),
    ]  # J5 is silent and not listed
    assert [m.meter_id for m, _ in await _service().top_consumers(None, 2)] == ["J3", "J2"]


async def test_top_consumers_tie_break_does_not_depend_on_input_order() -> None:
    meters, ts, rd = _fleet()

    async def backwards() -> list:  # type: ignore[type-arg]
        return sorted(meters.meters, key=lambda m: m.meter_id, reverse=True)

    meters.list_all = backwards  # type: ignore[method-assign]
    rows = await _service(fleet=(meters, ts, rd)).top_consumers(None, 10)
    assert [m.meter_id for m, _ in rows] == ["J3", "J2", "J1", "J4"]


async def test_top_consumers_node_and_limit_bounds() -> None:
    assert [m.meter_id for m, _ in await _service().top_consumers(DT2, 10)] == ["J3", "J4"]
    for bad in (0, 101):
        with pytest.raises(ValidationError):
            await _service().top_consumers(None, bad)
    with pytest.raises(NotFoundError):
        await _service().top_consumers("Z-09", 5)


# --- anomalies --------------------------------------------------------------------------------


class _FakeRule:
    """Emits canned anomalies per meter id so ordering and filtering are testable."""

    def __init__(self, rid: str, severity: Severity, per_meter: dict[str, list[int]]) -> None:
        self.id, self.severity, self.description = rid, severity, f"fake {rid}"
        self._per_meter = per_meter

    def evaluate(self, profile: MeterProfile) -> list[Anomaly]:
        return [
            Anomaly(
                self.id, self.severity, profile.meter.meter_id, "m", at(m) if m >= 0 else None, {}
            )
            for m in self._per_meter.get(profile.meter.meter_id, [])
        ]


def _fakes() -> list[_FakeRule]:
    return [
        _FakeRule("a_info", Severity.INFO, {"J1": [5]}),
        _FakeRule("b_error", Severity.ERROR, {"J2": [30, 10], "J1": [-1]}),
        _FakeRule("c_warn", Severity.WARNING, {"J1": [1], "J2": [2]}),
    ]


async def test_anomalies_ordered_severity_then_meter_then_time() -> None:
    report = await _service(rules=_fakes()).anomalies(None, None, None, 1, 50)
    got = [(a.rule, a.meter_id, a.at) for a in report.items.items]
    assert got == [
        ("b_error", "J1", None),
        ("b_error", "J2", at(10)),
        ("b_error", "J2", at(30)),
        ("c_warn", "J1", at(1)),
        ("c_warn", "J2", at(2)),
        ("a_info", "J1", at(5)),
    ]
    assert report.items.total == 6
    assert [(r.id, r.severity) for r in report.rules] == [
        ("a_info", Severity.INFO),
        ("b_error", Severity.ERROR),
        ("c_warn", Severity.WARNING),
    ]


async def test_anomalies_filters_and_paging() -> None:
    svc = _service(rules=_fakes())
    by_rule = await svc.anomalies("c_warn", None, None, 1, 50)
    assert {a.rule for a in by_rule.items.items} == {"c_warn"}
    by_sev = await svc.anomalies(None, Severity.ERROR, None, 1, 2)
    assert (len(by_sev.items.items), by_sev.items.total) == (2, 3)
    page2 = await svc.anomalies(None, Severity.ERROR, None, 2, 2)
    assert [a.at for a in page2.items.items] == [at(30)]
    # a rule filter and a conflicting severity filter intersect to nothing
    none = await svc.anomalies("c_warn", Severity.ERROR, None, 1, 50)
    assert none.items.total == 0


async def test_anomalies_node_filter_and_unknown_rule_and_node() -> None:
    report = await _service(rules=_fakes()).anomalies(None, None, DT2, 1, 50)
    assert report.items.total == 0  # J3/J4 emit nothing
    with pytest.raises(ValidationError) as exc:
        await _service().anomalies("nope", None, None, 1, 50)
    assert "inactive_but_consuming" in exc.value.details["valid"]  # type: ignore[operator]
    with pytest.raises(NotFoundError):
        await _service().anomalies(None, None, "Z-09", 1, 50)


async def test_real_rules_find_the_decommissioned_meter() -> None:
    report = await _service().anomalies("inactive_but_consuming", None, None, 1, 50)
    assert [a.meter_id for a in report.items.items] == ["J4"]


async def test_meter_anomalies() -> None:
    found = await _service().meter_anomalies("J4")
    assert [a.rule for a in found] == ["inactive_but_consuming"]
    assert await _service().meter_anomalies("J1") == []
    assert await _service().meter_anomalies("J5") == []  # silent meter: nothing to evaluate
    with pytest.raises(NotFoundError):
        await _service().meter_anomalies("J999")


# --- transformer load -------------------------------------------------------------------------


def _dt_fleet() -> tuple[FakeMeterRepository, FakeTransformerRepository, FakeReadingRepository]:
    """Estimated load fixture (kVAh = kWh, so kVA = 2 x kVAh per half hour).

    DT-001 (10 kVA): X steps 1,2,3  Y steps 3,1  Z daily (huge, ignored)
      half hour 00:00 -> X1 + Y3 = 4 kVAh = 8.0 kVA ; 00:30 -> 2 + 1 = 3 = 6.0 ; 01:00 -> 3 = 6.0
      peak 8.0 at 00:00, avg (8 + 6 + 6) / 3 = 6.667, utilisation 80.0 %
    DT-002 (100 kVA): only a daily meter -> nulls
    DT-003 (50 kVA): no meters -> nulls
    DT-004 (4 kVA): W steps 1 -> 2.0 kVA, 50.0 %
    DT-005 (7 kVA): V steps 4 -> 8.0 kVA, 114.29 % overloaded
    """
    ms = [
        make_meter("X", dt=("DT-001", "DT 1")),
        make_meter("Y", dt=("DT-001", "DT 1")),
        make_meter("Z", dt=("DT-001", "DT 1")),
        make_meter("D2", dt=("DT-002", "DT 2"), feeder=("F-002", "F 2")),
        make_meter("W", dt=("DT-004", "DT 4"), feeder=("F-004", "F 4")),
        make_meter("V", dt=("DT-005", "DT 5"), feeder=("F-005", "F 5")),
    ]
    rd = {
        "X": series([1.0, 2.0, 3.0], kvah_factor=1.0),
        "Y": series([3.0, 1.0], kvah_factor=1.0),
        "Z": series([500.0, 500.0], step_min=1440, kvah_factor=1.0),
        "D2": series([5.0, 5.0], step_min=1440),
        "W": series([1.0], kvah_factor=1.0),
        "V": series([4.0], kvah_factor=1.0),
    }
    ts = [
        Transformer("DT-001", "DT 1", "F-001", 10),
        Transformer("DT-002", "DT 2", "F-002", 100),
        Transformer("DT-003", "DT 3", "F-003", 50),
        Transformer("DT-004", "DT 4", "F-004", 4),
        Transformer("DT-005", "DT 5", "F-005", 7),
    ]
    return FakeMeterRepository(ms), FakeTransformerRepository(ts), FakeReadingRepository(rd)


async def test_transformer_load_estimates_and_sort_by_utilisation() -> None:
    rows = await _service(fleet=_dt_fleet()).transformer_load("utilisation", 40)
    assert [r.code for r in rows] == ["DT-005", "DT-001", "DT-004", "DT-002", "DT-003"]
    dt1 = rows[1]
    assert (dt1.capacity_kva, dt1.meter_count, dt1.half_hourly_meters) == (10, 3, 2)
    assert (dt1.peak_kva_est, dt1.avg_kva_est, dt1.peak_at) == (8.0, 6.667, T0)
    assert (dt1.utilisation_pct, dt1.overloaded) == (80.0, False)
    over = rows[0]
    assert (over.peak_kva_est, over.utilisation_pct, over.overloaded) == (8.0, 114.29, True)
    assert rows[2].utilisation_pct == 50.0
    daily_only, empty = rows[3], rows[4]
    assert (daily_only.meter_count, daily_only.half_hourly_meters) == (1, 0)
    for r in (daily_only, empty):
        assert (r.peak_kva_est, r.avg_kva_est, r.peak_at, r.utilisation_pct) == (None,) * 4
        assert r.overloaded is False
    assert empty.meter_count == 0


async def test_transformer_load_sort_by_code_and_limit() -> None:
    svc = _service(fleet=_dt_fleet())
    assert [r.code for r in await svc.transformer_load("code", 40)] == [
        "DT-001", "DT-002", "DT-003", "DT-004", "DT-005",
    ]  # fmt: skip
    assert [r.code for r in await svc.transformer_load("utilisation", 2)] == ["DT-005", "DT-001"]
    for bad in (0, 101):
        with pytest.raises(ValidationError):
            await svc.transformer_load("code", bad)
    with pytest.raises(ValidationError):
        await svc.transformer_load("sideways", 5)


async def test_transformer_load_exactly_at_capacity_is_not_overloaded() -> None:
    ms, ts, rd = _dt_fleet()
    ts.transformers[4] = Transformer("DT-005", "DT 5", "F-005", 8)  # 8.0 kVA peak on 8 kVA = 100 %
    row = (await _service(fleet=(ms, ts, rd)).transformer_load("code", 40))[4]
    assert (row.utilisation_pct, row.overloaded) == (100.0, False)


async def test_transformer_load_skips_gap_intervals_and_counts_them() -> None:
    # kVAh = kWh. G has a hole (readings at 150 and 180 missing): its interval starting 120
    # spans 90 min and is skipped (1 skipped); it covers starts 0,30,60,90,210,240,270.
    # H is complete: 10 intervals (starts 0..270) of 2.0 kVAh.
    # Starts covered by both: 1 + 2 = 3 kVAh = 6.0 kVA (7 of them); H alone (120,150,180):
    # 2 kVAh = 4.0 kVA (3). Peak 6.0, earliest at T0 (ties go to the earliest start);
    # avg = (7 x 6 + 3 x 4) / 10 = 5.4.
    ms = [make_meter("G", dt=("DT-001", "DT 1")), make_meter("H", dt=("DT-001", "DT 1"))]
    g = [r for r in series([1.0] * 10, kvah_factor=1.0) if r.at not in (at(150), at(180))]
    h = series([2.0] * 10, kvah_factor=1.0)
    ts = [Transformer("DT-001", "DT 1", "F-001", 10)]
    fleet = (
        FakeMeterRepository(ms),
        FakeTransformerRepository(ts),
        FakeReadingRepository({"G": g, "H": h}),
    )
    [row] = await _service(fleet=fleet).transformer_load("code", 40)
    assert row.skipped_gap_intervals == 1
    assert (row.peak_kva_est, row.avg_kva_est, row.peak_at) == (6.0, 5.4, T0)


async def test_transformer_load_without_gaps_skips_none() -> None:
    rows = await _service(fleet=_dt_fleet()).transformer_load("code", 40)
    assert all(r.skipped_gap_intervals == 0 for r in rows)


_ = (IST, Reading)
