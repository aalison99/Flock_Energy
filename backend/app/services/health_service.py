"""Readiness: derived from the circuit breaker alone (never calls the portal)."""

from app.portal.interfaces import BreakerState, BreakerStateReader
from app.services.results import ReadinessResult


class HealthService:
    def __init__(self, breaker: BreakerStateReader) -> None:
        self._breaker = breaker

    def readiness(self) -> ReadinessResult:
        state = self._breaker.state
        return ReadinessResult(ready=state is not BreakerState.OPEN, breaker=state)
