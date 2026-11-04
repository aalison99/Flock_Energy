"""Anomaly vocabulary: the finding, the rule Protocol and the thresholds rules are built with."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.services.analytics.profile import MeterProfile
from app.services.quality.models import Severity


@dataclass(frozen=True)
class AnomalyThresholds:
    """The tunable numbers, passed into rules at construction (from Settings in deps.py)."""

    voltage_min_v: float
    voltage_max_v: float
    flatline_hours: float
    spike_sigma: float
    spike_min_points: int
    inactive_min_kwh: float


@dataclass(frozen=True)
class Anomaly:
    rule: str
    severity: Severity
    meter_id: str
    message: str
    at: datetime | None
    evidence: Mapping[str, object]


class AnomalyRule(Protocol):
    id: str
    severity: Severity
    description: str

    def evaluate(self, profile: MeterProfile) -> list[Anomaly]: ...
