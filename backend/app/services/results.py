"""Service result types: plain frozen dataclasses (no pydantic)."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from app.domain.models import (
    GeoPoint,
    HierarchyLevel,
    Meter,
    PageResult,
    SyncRun,
    Transformer,
)
from app.portal.interfaces import BreakerState
from app.services.analytics.anomalies.models import Anomaly
from app.services.quality.models import Issue, Severity
from app.services.readings.buckets import Bucket, Resolution
from app.services.readings.series import IntervalKind, IntervalPoint


@dataclass(frozen=True)
class Meta:
    """Where an answer came from and how fresh it is."""

    source: Literal["portal", "index"]
    fetched_at: datetime
    stale: bool


@dataclass(frozen=True)
class MeterDetailResult:
    meter: Meter
    geo: GeoPoint | None
    meta: Meta


@dataclass(frozen=True)
class TransformerView:
    """A transformer plus how many indexed meters hang off it (None: index not ready)."""

    transformer: Transformer
    meter_count: int | None


@dataclass(frozen=True)
class IndexInfo:
    """What the local index holds: ready once it has at least one meter."""

    ready: bool
    meter_count: int
    last_sync_at: datetime | None


@dataclass(frozen=True)
class SyncStatusResult:
    latest: SyncRun | None
    last_successful: SyncRun | None


@dataclass(frozen=True)
class ReadinessResult:
    ready: bool
    breaker: BreakerState
    index: IndexInfo


@dataclass(frozen=True)
class ReadingSummary:
    total_kwh: float
    total_kvah: float
    avg_voltage: float | None
    readings: int
    gaps: int
    resets: int
    first_at: datetime | None
    last_at: datetime | None


@dataclass(frozen=True)
class ReadingSeriesResult:
    """Exactly one of `points` (raw) or `buckets` (hourly/daily) is set."""

    meter_id: str
    resolution: Resolution
    interval_minutes: int | None
    interval_kind: IntervalKind
    points: list[IntervalPoint] | None
    buckets: list[Bucket] | None
    summary: ReadingSummary
    meta: Meta


@dataclass(frozen=True)
class TreeNode:
    """A hierarchy node with subtree meter count and status split, plus depth-limited children."""

    id: str
    level: HierarchyLevel
    code: str
    name: str
    meter_count: int
    status_breakdown: dict[str, int]
    unplaced_count: int
    children: list["TreeNode"]


@dataclass(frozen=True)
class NodeSummary:
    """A node without its children: ancestors on a path, or a child in a listing."""

    id: str
    level: HierarchyLevel
    code: str
    name: str
    meter_count: int


@dataclass(frozen=True)
class AliasView:
    name: str
    meter_ids: tuple[str, ...]


@dataclass(frozen=True)
class NodeDetail:
    """One node: its breadcrumb path (root to itself), children, counts and alias names."""

    id: str
    level: HierarchyLevel
    code: str
    name: str
    path: list[NodeSummary]
    children: list[NodeSummary]
    meter_count: int
    status_breakdown: dict[str, int]
    unplaced_count: int
    alt_names: list[AliasView]


@dataclass(frozen=True)
class CheckInfo:
    id: str
    severity: Severity
    description: str


@dataclass(frozen=True)
class QualityReport:
    """Per-check counts and the check list (both unfiltered) plus one page of issues."""

    summary: dict[str, int]
    checks: list[CheckInfo]
    items: PageResult[Issue]


# --- analytics -------------------------------------------------------------------------------


@dataclass(frozen=True)
class FleetSummary:
    """Fleet-wide numbers from the indexed readings. Silent meters count as interval "unknown"."""

    total_meters: int
    meters_by_status: dict[str, int]
    reporting_meters: int
    silent_meters: int
    total_kwh: float
    first_reading_at: datetime | None
    last_reading_at: datetime | None
    anomalies_by_rule: dict[str, int]
    interval_kinds: dict[str, int]


@dataclass(frozen=True)
class ConsumptionBucket:
    start: datetime
    end: datetime
    kwh: float | None
    kvah: float | None
    meters: int


@dataclass(frozen=True)
class ConsumptionSeries:
    node: str | None
    resolution: Resolution
    meters_included: int
    meters_excluded_coarser: int
    items: list[ConsumptionBucket]


@dataclass(frozen=True)
class RuleInfo:
    id: str
    severity: Severity
    description: str


@dataclass(frozen=True)
class AnomalyReport:
    """One page of anomalies plus the rule list (unfiltered)."""

    rules: list[RuleInfo]
    items: PageResult[Anomaly]


@dataclass(frozen=True)
class DtLoad:
    """Estimated transformer loading from half-hourly kVAh (an estimate, see AnalyticsService)."""

    code: str
    name: str
    capacity_kva: int
    meter_count: int
    half_hourly_meters: int
    skipped_gap_intervals: int
    peak_kva_est: float | None
    avg_kva_est: float | None
    peak_at: datetime | None
    utilisation_pct: float | None
    overloaded: bool
