import pytest

from app.portal.interfaces import BreakerState
from app.services.health_service import HealthService
from tests.support.fakes import FakeBreaker


@pytest.mark.parametrize(
    ("state", "ready"),
    [(BreakerState.CLOSED, True), (BreakerState.HALF_OPEN, True), (BreakerState.OPEN, False)],
)
def test_readiness_by_breaker_state(state: BreakerState, ready: bool) -> None:
    result = HealthService(FakeBreaker(state)).readiness()
    assert result.ready is ready
    assert result.breaker is state


def test_readiness_takes_no_portal(monkeypatch: pytest.MonkeyPatch) -> None:
    # The service is constructed from the breaker alone: it has no portal to call.
    service = HealthService(FakeBreaker())
    assert not hasattr(service, "_portal")
    assert service.readiness().ready
