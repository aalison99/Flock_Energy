"""Hand-made readings, meters and profiles for analytics tests."""

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

from app.domain.models import InstallStatus, Meter, Reading
from app.services.analytics.profile import MeterProfile, profile_meter
from tests.support.hierarchy_factory import make_meter

IST = timezone(timedelta(hours=5, minutes=30))
T0 = datetime(2026, 6, 1, 0, 0, tzinfo=IST)


def at(minutes: int, base: datetime = T0) -> datetime:
    return base + timedelta(minutes=minutes)


def series(
    kwh_steps: Sequence[float],
    *,
    step_min: int = 30,
    kvah_factor: float = 1.25,
    voltages: Sequence[float | None] | None = None,
    start_kwh: float = 100.0,
    base: datetime = T0,
) -> list[Reading]:
    """Cumulative readings: reading 0 at `base`, then one per step adding kwh_steps[i].

    A negative step lowers the register (a reset). kVAh is kwh * kvah_factor.
    """
    out: list[Reading] = []
    kwh = start_kwh
    volts = list(voltages) if voltages is not None else [230.0] * (len(kwh_steps) + 1)
    out.append(Reading(base, kwh, round(kwh * kvah_factor, 3), volts[0]))
    for i, step in enumerate(kwh_steps, start=1):
        kwh = round(kwh + step, 3)
        out.append(
            Reading(
                base + timedelta(minutes=step_min * i), kwh, round(kwh * kvah_factor, 3), volts[i]
            )
        )
    return out


def meter(
    meter_id: str = "J1", status: InstallStatus = InstallStatus.INSTALLED, **kw: object
) -> Meter:
    return make_meter(meter_id, status=status, **kw)  # type: ignore[arg-type]


def profile(
    readings: Sequence[Reading],
    *,
    meter_id: str = "J1",
    status: InstallStatus = InstallStatus.INSTALLED,
) -> MeterProfile:
    return profile_meter(meter(meter_id, status), readings)
