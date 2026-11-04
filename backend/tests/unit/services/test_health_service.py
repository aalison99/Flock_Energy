from datetime import UTC, datetime

import pytest

from app.portal.interfaces import BreakerState
from app.services.health_service import HealthService
from app.services.results import IndexInfo
from tests.support.fakes import FakeBreaker, FakeIndexReader

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize(
    ("state", "ready"),
    [(BreakerState.CLOSED, True), (BreakerState.HALF_OPEN, True), (BreakerState.OPEN, False)],
)
async def test_readiness_by_breaker_state(state: BreakerState, ready: bool) -> None:
    result = await HealthService(FakeBreaker(state), FakeIndexReader()).readiness()
    assert result.ready is ready
    assert result.breaker is state


async def test_empty_index_does_not_make_the_service_unready() -> None:
    result = await HealthService(FakeBreaker(), FakeIndexReader()).readiness()
    assert result.ready
    assert result.index == IndexInfo(ready=False, meter_count=0, last_sync_at=None)


async def test_readiness_carries_the_index_info() -> None:
    info = IndexInfo(ready=True, meter_count=403, last_sync_at=datetime(2026, 11, 4, tzinfo=UTC))
    result = await HealthService(FakeBreaker(), FakeIndexReader(info)).readiness()
    assert result.index == info


async def test_readiness_takes_no_portal() -> None:
    # The service is constructed from the breaker and an index reader: it has no portal to call.
    service = HealthService(FakeBreaker(), FakeIndexReader())
    assert not hasattr(service, "_portal")
    assert (await service.readiness()).ready
