"""Small fakes of the read-only portal views used by service and API tests."""

from datetime import datetime

from app.portal.interfaces import BreakerState, Freshness
from app.services.results import IndexInfo


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
