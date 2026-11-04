"""Analytics response schemas and the mappings from service results."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.api.v1.schemas.hierarchy import StatusBreakdown
from app.api.v1.schemas.meters import MeterSummary, to_meter_summary
from app.core.pagination import Page
from app.domain.models import Meter
from app.services.analytics.anomalies.models import Anomaly
from app.services.quality.models import Severity
from app.services.results import (
    ConsumptionBucket,
    ConsumptionSeries,
    DtLoad,
    FleetSummary,
    RuleInfo,
)

ESTIMATE_NOTE = (
    "Estimate, not a measurement. For each DT, over its half-hourly meters only, the kVAh "
    "consumed in each half hour is summed across meters and multiplied by 2 to give apparent "
    "power in kVA for that half hour. peak_kva_est is the largest such value, avg_kva_est the "
    "mean over half hours with at least one contributing meter, and utilisation_pct is the peak "
    "over capacity_kva. Intervals that span a data gap are left out rather than invented "
    "(counted in skipped_gap_intervals). A DT's meters are those whose own dt_code names it, "
    "which can differ from the hierarchy path. It ignores network losses, meters that are not "
    "half-hourly, load diversity and power factor, so real loading can differ."
)


class FleetSummaryOut(BaseModel):
    """Fleet-wide figures computed from the indexed readings."""

    total_meters: int = Field(description="Meters in the local index.")
    meters_by_status: StatusBreakdown = Field(
        description="Fleet meters per installation status, every status listed."
    )
    reporting_meters: int = Field(description="Meters with at least two readings.")
    silent_meters: int = Field(description="Meters with fewer than two readings.")
    total_kwh: float = Field(description="Energy consumed over the indexed window, in kWh.")
    first_reading_at: datetime | None = Field(
        description="Earliest reading instant (IST); null when no meter reports."
    )
    last_reading_at: datetime | None = Field(
        description="Latest reading instant (IST); null when no meter reports."
    )
    anomalies_by_rule: dict[str, int] = Field(
        description="Anomaly count per rule id, zero-filled for every registered rule."
    )
    interval_kinds: dict[str, int] = Field(
        description="Meters per reading cadence: half_hourly, daily or unknown "
        "(unknown includes silent meters)."
    )


def to_fleet_summary_out(s: FleetSummary) -> FleetSummaryOut:
    return FleetSummaryOut(
        total_meters=s.total_meters,
        meters_by_status=StatusBreakdown(**s.meters_by_status),
        reporting_meters=s.reporting_meters,
        silent_meters=s.silent_meters,
        total_kwh=s.total_kwh,
        first_reading_at=s.first_reading_at,
        last_reading_at=s.last_reading_at,
        anomalies_by_rule=s.anomalies_by_rule,
        interval_kinds=s.interval_kinds,
    )


class ConsumptionBucketOut(BaseModel):
    """Energy summed over the contributing meters for one hour or day."""

    start: datetime = Field(description="Bucket start (IST).")
    end: datetime = Field(description="Bucket end, exclusive (IST).")
    kwh: float | None = Field(description="Active energy in kWh.")
    kvah: float | None = Field(description="Apparent energy in kVAh.")
    meters: int = Field(description="Meters that contributed to this bucket.")


class ConsumptionResponse(BaseModel):
    """Consumption per hour or day across a node's meters (or the whole fleet)."""

    node: str | None = Field(description="The node filter that was applied, if any.")
    resolution: Literal["hourly", "daily"] = Field(description="Bucket width.")
    meters_included: int = Field(description="Meters whose cadence fits the resolution.")
    meters_excluded_coarser: int = Field(
        description="Reporting meters left out because their interval is coarser than the bucket."
    )
    items: list[ConsumptionBucketOut] = Field(description="Buckets, ascending by start.")


def to_consumption_response(c: ConsumptionSeries) -> ConsumptionResponse:
    def bucket(b: ConsumptionBucket) -> ConsumptionBucketOut:
        return ConsumptionBucketOut(
            start=b.start, end=b.end, kwh=b.kwh, kvah=b.kvah, meters=b.meters
        )

    return ConsumptionResponse(
        node=c.node,
        resolution="hourly" if c.resolution.value == "hourly" else "daily",
        meters_included=c.meters_included,
        meters_excluded_coarser=c.meters_excluded_coarser,
        items=[bucket(b) for b in c.items],
    )


class TopConsumerOut(BaseModel):
    """A meter and its total consumption."""

    meter: MeterSummary = Field(description="The meter.")
    total_kwh: float = Field(description="Energy consumed over the indexed window, in kWh.")


class TopConsumersResponse(BaseModel):
    """Meters ordered by consumption, highest first."""

    items: list[TopConsumerOut] = Field(description="Top consumers.")


def to_top_consumers_response(rows: list[tuple[Meter, float]]) -> TopConsumersResponse:
    return TopConsumersResponse(
        items=[TopConsumerOut(meter=to_meter_summary(m), total_kwh=kwh) for m, kwh in rows]
    )


class AnomalyOut(BaseModel):
    """One rule finding for one meter."""

    rule: str = Field(description="Id of the rule that fired.")
    severity: Severity = Field(description="Severity of the rule.")
    meter_id: str = Field(description="Meter the finding is about.")
    message: str = Field(description="Human-readable summary.")
    at: datetime | None = Field(description="Instant of the finding (IST); null when not dated.")
    evidence: dict[str, object] = Field(description="Rule-specific facts behind the finding.")


def to_anomaly_out(a: Anomaly) -> AnomalyOut:
    return AnomalyOut(
        rule=a.rule,
        severity=a.severity,
        meter_id=a.meter_id,
        message=a.message,
        at=a.at,
        evidence=dict(a.evidence),
    )


class RuleOut(BaseModel):
    """One registered anomaly rule."""

    id: str = Field(description="Rule id, usable as the `rule` filter.")
    severity: Severity = Field(description="Severity of findings from this rule.")
    description: str = Field(description="What the rule looks for.")


def to_rule_out(r: RuleInfo) -> RuleOut:
    return RuleOut(id=r.id, severity=r.severity, description=r.description)


class AnomalyListResponse(Page[AnomalyOut]):
    """A page of anomalies plus the rule list."""

    rules: list[RuleOut] = Field(description="Every registered rule, regardless of filters.")


class MeterAnomaliesResponse(BaseModel):
    """Every anomaly of one meter."""

    meter_id: str = Field(description="The meter.")
    items: list[AnomalyOut] = Field(description="Findings, most severe first.")


class DtLoadOut(BaseModel):
    """Estimated loading of one distribution transformer."""

    code: str = Field(description="DT code.")
    name: str = Field(description="DT name.")
    capacity_kva: int = Field(description="Rated capacity in kVA.")
    meter_count: int = Field(description="Indexed meters on this DT.")
    half_hourly_meters: int = Field(description="Of those, meters reporting half-hourly.")
    skipped_gap_intervals: int = Field(
        description="Half-hourly intervals left out of the estimate because they span a data gap."
    )
    peak_kva_est: float | None = Field(
        description="Estimated peak apparent power in kVA; null without half-hourly data."
    )
    avg_kva_est: float | None = Field(description="Estimated average apparent power in kVA.")
    peak_at: datetime | None = Field(description="Start of the peak half hour (IST).")
    utilisation_pct: float | None = Field(description="Peak as a percentage of capacity.")
    overloaded: bool = Field(description="True when utilisation_pct exceeds 100.")


class TransformerLoadResponse(BaseModel):
    """Estimated DT loading, with the formula behind it."""

    estimate_note: str = Field(description="How the estimate is computed and what it ignores.")
    items: list[DtLoadOut] = Field(description="Transformers in the requested order.")


def to_transformer_load_response(rows: list[DtLoad]) -> TransformerLoadResponse:
    return TransformerLoadResponse(
        estimate_note=ESTIMATE_NOTE,
        items=[DtLoadOut.model_validate(r, from_attributes=True) for r in rows],
    )
