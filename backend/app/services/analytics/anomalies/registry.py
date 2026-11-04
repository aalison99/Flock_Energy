"""The registered anomaly rules: add a class to RULE_CLASSES to add a rule."""

from app.services.analytics.anomalies.models import AnomalyRule, AnomalyThresholds
from app.services.analytics.anomalies.rules import (
    ConsumptionSpike,
    DataGap,
    Flatline,
    InactiveButConsuming,
    RegisterReset,
    VoltageOutOfBand,
)

RULE_CLASSES = (
    InactiveButConsuming,
    VoltageOutOfBand,
    Flatline,
    RegisterReset,
    DataGap,
    ConsumptionSpike,
)


def build_rules(thresholds: AnomalyThresholds) -> tuple[AnomalyRule, ...]:
    """Every registered rule, constructed with the thresholds."""
    return tuple(cls(thresholds) for cls in RULE_CLASSES)
