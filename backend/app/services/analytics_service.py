"""Fleet analytics computed from the indexed readings (never the portal).

Everything is computed per request from the local index (about 16k readings today). Beyond
roughly 1M readings, precompute the per-meter aggregates at sync time instead.
"""

from collections import Counter, defaultdict
from collections.abc import Collection, Sequence
from datetime import datetime
from typing import Literal

from app.domain.exceptions import IndexNotReadyError, NotFoundError, ValidationError
from app.domain.models import InstallStatus, Meter, PageResult, Transformer
from app.repositories.interfaces import MeterRepository, ReadingRepository, TransformerRepository
from app.services.analytics.anomalies.models import Anomaly, AnomalyRule
from app.services.analytics.profile import MeterProfile, profile_meter
from app.services.hierarchy.builder import build_hierarchy, subtree_meter_ids
from app.services.quality.models import SEVERITY_ORDER, Severity
from app.services.readings.buckets import BUCKET_MINUTES, Resolution, aggregate
from app.services.readings.series import GAP, INTERVAL_KINDS
from app.services.results import (
    AnomalyReport,
    ConsumptionBucket,
    ConsumptionSeries,
    DtLoad,
    FleetSummary,
    RuleInfo,
)

LoadSort = Literal["utilisation", "code"]
HALF_HOUR = 30
MAX_LIMIT = 100
_RANK = {severity: rank for rank, severity in enumerate(SEVERITY_ORDER)}


def _check_limit(limit: int) -> None:
    if not 1 <= limit <= MAX_LIMIT:
        raise ValidationError(f"limit must be between 1 and {MAX_LIMIT}", details={"limit": limit})


def _anomaly_key(a: Anomaly) -> tuple[int, str, int, float]:
    # Undated findings first within a meter; then by instant.
    return (
        _RANK[a.severity],
        a.meter_id,
        0 if a.at is None else 1,
        a.at.timestamp() if a.at else 0,
    )


class AnalyticsService:
    def __init__(
        self,
        meters: MeterRepository,
        transformers: TransformerRepository,
        readings: ReadingRepository,
        rules: Sequence[AnomalyRule],
    ) -> None:
        self._meters = meters
        self._transformers = transformers
        self._readings = readings
        self._rules = rules

    # --- loading -------------------------------------------------------------------------

    async def _all_meters(self) -> list[Meter]:
        meters = await self._meters.list_all()
        if not meters:
            raise IndexNotReadyError("the local index is empty; a sync is needed")
        return meters

    async def _profiles(self, node: str | None) -> list[MeterProfile]:
        """Profiles (ordered by meter id) of every meter, or of those under the hierarchy node."""
        meters = await self._all_meters()
        ids: Collection[str] | None = None
        if node is not None:
            snapshot = build_hierarchy(meters, await self._transformers.list_all())
            if node not in snapshot.nodes:
                raise NotFoundError(f"hierarchy node {node} not found")
            ids = set(subtree_meter_ids(snapshot, node))
            meters = [m for m in meters if m.meter_id in ids]
        by_meter = await self._readings.list_for_meters(ids, None, None)
        return [profile_meter(m, by_meter.get(m.meter_id, [])) for m in meters]

    def _anomalies_of(self, profile: MeterProfile) -> list[Anomaly]:
        return [a for rule in self._rules for a in rule.evaluate(profile)]

    # --- use cases -----------------------------------------------------------------------

    async def summary(self) -> FleetSummary:
        profiles = await self._profiles(None)
        reporting = [p for p in profiles if p.reporting]
        firsts = [p.first_at for p in reporting if p.first_at is not None]
        lasts = [p.last_at for p in reporting if p.last_at is not None]
        by_rule: Counter[str] = Counter(a.rule for p in profiles for a in self._anomalies_of(p))
        statuses = Counter(p.meter.install_status.value for p in profiles)
        kinds = Counter(p.interval_kind for p in profiles)
        return FleetSummary(
            total_meters=len(profiles),
            meters_by_status={s.value: statuses.get(s.value, 0) for s in InstallStatus},
            reporting_meters=len(reporting),
            silent_meters=len(profiles) - len(reporting),
            total_kwh=round(sum(p.total_kwh for p in profiles), 3),
            first_reading_at=min(firsts) if firsts else None,
            last_reading_at=max(lasts) if lasts else None,
            anomalies_by_rule={r.id: by_rule.get(r.id, 0) for r in self._rules},
            interval_kinds={k: kinds.get(k, 0) for k in (*INTERVAL_KINDS.values(), "unknown")},
        )

    async def consumption(self, node: str | None, resolution: Resolution) -> ConsumptionSeries:
        """Sum bucketed kWh/kVAh over the node's meters.

        A meter whose interval is coarser than the bucket is excluded (and counted); meters
        without two readings are neither included nor excluded.
        """
        width = BUCKET_MINUTES.get(resolution)
        if width is None:
            raise ValidationError(
                f"resolution '{resolution}' is not offered; use hourly or daily",
                details={"valid": ["hourly", "daily"]},
            )
        profiles = [p for p in await self._profiles(node) if p.reporting]
        usable = [
            p for p in profiles if p.interval_minutes is not None and p.interval_minutes <= width
        ]
        sums: dict[datetime, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
        ends: dict[datetime, datetime] = {}
        for p in usable:
            for b in aggregate(p.points, resolution):
                if b.kwh is None and b.kvah is None:
                    continue
                acc = sums[b.start]
                acc[0] += b.kwh or 0.0
                acc[1] += b.kvah or 0.0
                acc[2] += 1
                ends[b.start] = b.end
        return ConsumptionSeries(
            node=node,
            resolution=resolution,
            meters_included=len(usable),
            meters_excluded_coarser=len(profiles) - len(usable),
            items=[
                ConsumptionBucket(s, ends[s], round(v[0], 3), round(v[1], 3), int(v[2]))
                for s, v in sorted(sums.items())
            ],
        )

    async def top_consumers(self, node: str | None, limit: int) -> list[tuple[Meter, float]]:
        """Reporting meters by total kWh, highest first, ties by meter id."""
        _check_limit(limit)
        ranked = sorted(
            (p for p in await self._profiles(node) if p.reporting),
            key=lambda p: (-p.total_kwh, p.meter.meter_id),
        )
        return [(p.meter, p.total_kwh) for p in ranked[:limit]]

    async def anomalies(
        self,
        rule: str | None,
        severity: Severity | None,
        node: str | None,
        page: int,
        page_size: int,
    ) -> AnomalyReport:
        valid = [r.id for r in self._rules]
        if rule is not None and rule not in valid:
            raise ValidationError(f"unknown rule {rule}", details={"valid": valid})
        found = [
            a
            for p in await self._profiles(node)
            for a in self._anomalies_of(p)
            if (rule is None or a.rule == rule) and (severity is None or a.severity == severity)
        ]
        found.sort(key=_anomaly_key)
        start = (page - 1) * page_size
        return AnomalyReport(
            rules=[RuleInfo(r.id, r.severity, r.description) for r in self._rules],
            items=PageResult(items=found[start : start + page_size], total=len(found)),
        )

    async def meter_anomalies(self, meter_id: str) -> list[Anomaly]:
        if await self._meters.count() == 0:
            raise IndexNotReadyError("the local index is empty; a sync is needed")
        meter = await self._meters.get(meter_id)
        if meter is None:
            raise NotFoundError(f"meter {meter_id} not found")
        by_meter = await self._readings.list_for_meters([meter_id], None, None)
        found = self._anomalies_of(profile_meter(meter, by_meter.get(meter_id, [])))
        return sorted(found, key=_anomaly_key)

    async def transformer_load(self, sort: str, limit: int) -> list[DtLoad]:
        """Estimated DT loading (an estimate, not a measurement).

        Over a DT's half-hourly meters, the kVAh of each half hour summed across meters and
        multiplied by 2 is the apparent power in kVA for that half hour. Daily meters are
        ignored, and so are intervals that span a data gap (counted in `skipped_gap_intervals`;
        pro-rating them would invent data). A DT's meters are those whose own `dt_code` names
        it, which can differ from the hierarchy path. Losses, diversity and power factor are
        not modelled.
        """
        _check_limit(limit)
        if sort not in ("utilisation", "code"):
            raise ValidationError(
                f"unknown sort {sort}", details={"valid": ["utilisation", "code"]}
            )
        profiles = await self._profiles(None)
        transformers = await self._transformers.list_all()
        by_dt: dict[str, list[MeterProfile]] = defaultdict(list)
        for p in profiles:
            if p.meter.dt_code is not None:
                by_dt[p.meter.dt_code].append(p)
        rows = [self._dt_load(t, by_dt.get(t.code, [])) for t in transformers]
        if sort == "code":
            rows.sort(key=lambda r: r.code)
        else:
            rows.sort(
                key=lambda r: (r.utilisation_pct is None, -(r.utilisation_pct or 0.0), r.code)
            )
        return rows[:limit]

    @staticmethod
    def _dt_load(t: Transformer, members: list[MeterProfile]) -> DtLoad:
        half_hourly = [p for p in members if p.interval_minutes == HALF_HOUR]
        kva: dict[datetime, float] = defaultdict(float)
        skipped = 0
        for p in half_hourly:
            for pt in p.points:
                if pt.start is None or pt.kvah is None:
                    continue
                if GAP in pt.flags:
                    skipped += 1
                    continue
                kva[pt.start] += pt.kvah * (60 / HALF_HOUR)
        peak_at: datetime | None = None
        peak = avg = util = None
        if kva:
            peak_at = min(kva, key=lambda s: (-kva[s], s))  # ties: the earliest half hour
            peak = round(kva[peak_at], 3)
            avg = round(sum(kva.values()) / len(kva), 3)
            if t.capacity_kva > 0:
                util = round(kva[peak_at] / t.capacity_kva * 100, 2)
        return DtLoad(
            code=t.code,
            name=t.name,
            capacity_kva=t.capacity_kva,
            meter_count=len(members),
            half_hourly_meters=len(half_hourly),
            peak_kva_est=peak,
            avg_kva_est=avg,
            skipped_gap_intervals=skipped,
            peak_at=peak_at,
            utilisation_pct=util,
            overloaded=util is not None and util > 100,
        )
