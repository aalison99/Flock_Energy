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
