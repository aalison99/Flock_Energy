"""Small fakes of the read-only portal views used by service and API tests."""

from collections import Counter
from collections.abc import Collection
from datetime import date, datetime

from app.domain.models import Meter, PageResult, Reading, Transformer
from app.portal.interfaces import BreakerState, Freshness
from app.repositories.interfaces import MeterQuery
from app.services.results import IndexInfo
from tests.support import meter_oracle


class FakeFreshness:
    """FreshnessReader returning canned entries keyed by (method, args); None when unknown."""

    def __init__(self) -> None:
        self.entries: dict[tuple[str, tuple[object, ...]], Freshness] = {}

    def set(
        self, method: str, *args: object, fetched_at: datetime, expires_at: datetime, stale: bool
    ) -> None:
        self.entries[(method, args)] = Freshness(fetched_at, expires_at, stale)

    def freshness(self, method: str, *args: object) -> Freshness | None:
        return self.entries.get((method, args))


class FakeBreaker:
    """BreakerStateReader with a settable state."""

    def __init__(self, state: BreakerState = BreakerState.CLOSED) -> None:
        self.state = state


class FakeIndexReader:
    """IndexStatusReader returning a settable IndexInfo."""

    def __init__(self, info: IndexInfo | None = None) -> None:
        self.info = info or IndexInfo(ready=False, meter_count=0, last_sync_at=None)

    async def index_info(self) -> IndexInfo:
        return self.info


class FakeMeterRepository:
    """MeterRepository over a plain list, answering queries with the brute-force oracle."""

    def __init__(self, meters: list[Meter] | None = None, synced_at: datetime | None = None):
        self.meters = list(meters or [])
        self.synced_at = synced_at
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    async def count(self) -> int:
        return len(self.meters)

    async def list_all(self) -> list[Meter]:
        return sorted(self.meters, key=lambda m: m.meter_id)

    async def get(self, meter_id: str) -> Meter | None:
        return next((m for m in self.meters if m.meter_id == meter_id), None)

    async def search(self, filters: MeterQuery, page: int, page_size: int) -> PageResult[Meter]:
        self.calls.append(("search", (filters, page, page_size)))
        found = meter_oracle.search(self.meters, filters)
        start = (page - 1) * page_size
        return PageResult(items=found[start : start + page_size], total=len(found))

    async def facet_counts(self, filters: MeterQuery, field: str) -> dict[str, int]:
        self.calls.append(("facet_counts", (filters, field)))
        values = (
            meter_oracle.FACET_VALUE[field](m) for m in meter_oracle.search(self.meters, filters)
        )
        return dict(Counter(v for v in values if v is not None))

    async def get_synced_at(self, meter_id: str) -> datetime | None:
        return self.synced_at if await self.get(meter_id) else None

    async def within_box(
        self,
        min_lat: float,
        min_lng: float,
        max_lat: float,
        max_lng: float,
        filters: MeterQuery,
        limit: int,
    ) -> list[Meter]:
        self.calls.append(("within_box", (min_lat, min_lng, max_lat, max_lng, filters, limit)))
        return [
            m
            for m in meter_oracle.search(self.meters, filters)
            if m.geo is not None
            and min_lat <= m.geo.lat <= max_lat
            and min_lng <= m.geo.lng <= max_lng
        ][:limit]


class FakeTransformerRepository:
    """TransformerRepository over a plain list."""

    def __init__(self, transformers: list[Transformer] | None = None) -> None:
        self.transformers = list(transformers or [])

    async def list_all(self) -> list[Transformer]:
        return sorted(self.transformers, key=lambda t: t.code)

    async def get(self, code: str) -> Transformer | None:
        return next((t for t in self.transformers if t.code == code), None)

    async def count(self) -> int:
        return len(self.transformers)


class FakeReadingRepository:
    """ReadingRepository over a dict of readings per meter (only list_for_meters is used)."""

    def __init__(self, by_meter: dict[str, list[Reading]] | None = None) -> None:
        self.by_meter = dict(by_meter or {})
        self.calls: list[Collection[str] | None] = []

    async def list_for_meters(
        self, meter_ids: Collection[str] | None, start: date | None, end: date | None
    ) -> dict[str, list[Reading]]:
        self.calls.append(None if meter_ids is None else set(meter_ids))
        keep = (
            self.by_meter
            if meter_ids is None
            else {k: v for k, v in self.by_meter.items() if k in set(meter_ids)}
        )
        return {
            k: sorted(
                (
                    r
                    for r in v
                    if (start is None or r.at.date() >= start)
                    and (end is None or r.at.date() <= end)
                ),
                key=lambda r: r.at,
            )
            for k, v in sorted(keep.items())
        }
