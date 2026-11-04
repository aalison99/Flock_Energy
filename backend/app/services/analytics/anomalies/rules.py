"""The anomaly rules. Each looks only at one MeterProfile; the interval maths is not repeated."""

from datetime import datetime
from statistics import fmean, pstdev

from app.domain.models import InstallStatus
from app.services.analytics.anomalies.models import Anomaly, AnomalyThresholds
from app.services.analytics.profile import MeterProfile
from app.services.quality.models import Severity
from app.services.readings.series import GAP, RESET, IntervalPoint, missing_intervals

_INACTIVE = (InstallStatus.FAULTY, InstallStatus.DECOMMISSIONED)


class InactiveButConsuming:
    id = "inactive_but_consuming"
    severity = Severity.ERROR
    description = "A faulty or decommissioned meter whose register still advances."

    def __init__(self, th: AnomalyThresholds) -> None:
        self._min_kwh = th.inactive_min_kwh

    def evaluate(self, profile: MeterProfile) -> list[Anomaly]:
        status = profile.meter.install_status
        if status not in _INACTIVE or profile.total_kwh <= self._min_kwh:
            return []
        return [
            Anomaly(
                self.id,
                self.severity,
                profile.meter.meter_id,
                f"{status.value} meter consumed {profile.total_kwh} kWh",
                None,
                {"install_status": status.value, "total_kwh": profile.total_kwh},
            )
        ]


class VoltageOutOfBand:
    id = "voltage_out_of_band"
    severity = Severity.WARNING
    description = "Phase-R voltage outside the allowed band; one finding per contiguous run."

    def __init__(self, th: AnomalyThresholds) -> None:
        self._lo, self._hi = th.voltage_min_v, th.voltage_max_v

    def _outside(self, p: IntervalPoint) -> bool:
        return p.voltage_r is not None and not self._lo <= p.voltage_r <= self._hi

    def evaluate(self, profile: MeterProfile) -> list[Anomaly]:
        runs: list[list[IntervalPoint]] = []
        previous_outside = False
        for point in profile.points:  # a reading inside the band, or without voltage, ends a run
            outside = self._outside(point)
            if outside:
                if previous_outside:
                    runs[-1].append(point)
                else:
                    runs.append([point])
            previous_outside = outside
        found: list[Anomaly] = []
        for run in runs:
            volts = [p.voltage_r for p in run if p.voltage_r is not None]
            found.append(
                Anomaly(
                    self.id,
                    self.severity,
                    profile.meter.meter_id,
                    f"{len(run)} reading(s) outside {self._lo}-{self._hi} V "
                    f"({min(volts)}-{max(volts)} V)",
                    run[0].at,
                    {
                        "first_at": run[0].at.isoformat(),
                        "last_at": run[-1].at.isoformat(),
                        "min_v": min(volts),
                        "max_v": max(volts),
                        "count": len(run),
                    },
                )
            )
        return found


class Flatline:
    id = "flatline"
    severity = Severity.WARNING
    description = "An installed meter with a long unbroken span of zero-kWh intervals."

    def __init__(self, th: AnomalyThresholds) -> None:
        self._hours = th.flatline_hours

    def _anomaly(self, profile: MeterProfile, span: list[IntervalPoint]) -> Anomaly | None:
        first, last = span[0], span[-1]
        assert first.start is not None
        hours = (last.at - first.start).total_seconds() / 3600
        if hours < self._hours:
            return None
        return Anomaly(
            self.id,
            self.severity,
            profile.meter.meter_id,
            f"no consumption for {round(hours, 2)} h",
            first.start,
            {
                "start": first.start.isoformat(),
                "end": last.at.isoformat(),
                "hours": round(hours, 3),
            },
        )

    def evaluate(self, profile: MeterProfile) -> list[Anomaly]:
        if profile.meter.install_status is not InstallStatus.INSTALLED:
            return []
        spans: list[list[IntervalPoint]] = [[]]
        for point in profile.points[1:]:  # the first reading has no interval
            if point.kwh == 0:
                spans[-1].append(point)
            elif spans[-1]:
                spans.append([])
        found = [self._anomaly(profile, s) for s in spans if s]
        return [a for a in found if a is not None]


class RegisterReset:
    id = "register_reset"
    severity = Severity.WARNING
    description = "The cumulative register went backwards between two readings."

    def __init__(self, th: AnomalyThresholds) -> None:
        pass

    def evaluate(self, profile: MeterProfile) -> list[Anomaly]:
        found: list[Anomaly] = []
        pairs = zip(profile.points, profile.points[1:], strict=False)
        for before, point in pairs:
            if RESET in point.flags:
                found.append(
                    Anomaly(
                        self.id,
                        self.severity,
                        profile.meter.meter_id,
                        f"kWh register fell from {before.kwh_register} to {point.kwh_register}",
                        point.at,
                        {
                            "previous_kwh_register": before.kwh_register,
                            "kwh_register": point.kwh_register,
                            "previous_at": before.at.isoformat(),
                        },
                    )
                )
        return found


class DataGap:
    id = "data_gap"
    severity = Severity.INFO
    description = "Readings missing between two consecutive readings."

    def __init__(self, th: AnomalyThresholds) -> None:
        pass

    def evaluate(self, profile: MeterProfile) -> list[Anomaly]:
        found: list[Anomaly] = []
        for point in profile.points:
            if GAP in point.flags and point.start is not None:
                missing = missing_intervals(
                    (point.at - point.start).total_seconds() / 60, profile.interval_minutes
                )
                found.append(
                    Anomaly(
                        self.id,
                        self.severity,
                        profile.meter.meter_id,
                        f"{missing} reading(s) missing before {point.at.isoformat()}",
                        point.at,
                        {"missing": missing, "from": point.start.isoformat()},
                    )
                )
        return found


class ConsumptionSpike:
    id = "consumption_spike"
    severity = Severity.WARNING
    description = "An interval's kWh far above the meter's own mean (mean + sigma x stdev)."

    def __init__(self, th: AnomalyThresholds) -> None:
        self._sigma, self._min_points = th.spike_sigma, th.spike_min_points

    def evaluate(self, profile: MeterProfile) -> list[Anomaly]:
        # A gap-flagged interval holds several intervals of energy: not comparable, so skipped.
        usable = [p for p in profile.points if GAP not in p.flags]
        values = [p.kwh for p in usable if p.kwh is not None]
        if len(values) < self._min_points:
            return []
        mean, sd = fmean(values), pstdev(values)
        if sd <= 0:
            return []
        limit = mean + self._sigma * sd
        found: list[Anomaly] = []
        for point in usable:
            if point.kwh is not None and point.kwh > limit:
                at: datetime = point.at
                found.append(
                    Anomaly(
                        self.id,
                        self.severity,
                        profile.meter.meter_id,
                        f"{point.kwh} kWh against a typical {round(mean, 3)} kWh",
                        at,
                        {
                            "kwh": point.kwh,
                            "mean": round(mean, 3),
                            "stdev": round(sd, 3),
                            "threshold": round(limit, 3),
                        },
                    )
                )
        return found
