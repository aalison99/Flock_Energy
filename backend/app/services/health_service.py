"""Readiness: decided by the circuit breaker alone (never calls the portal); reports the index."""

from app.portal.interfaces import BreakerState, BreakerStateReader
from app.services.interfaces import IndexStatusReader
from app.services.results import ReadinessResult


class HealthService:
    def __init__(self, breaker: BreakerStateReader, index: IndexStatusReader) -> None:
        self._breaker = breaker
        self._index = index

    async def readiness(self) -> ReadinessResult:
        state = self._breaker.state
        # An empty index is reported, not a failure: the API can still answer from the portal.
        return ReadinessResult(
            ready=state is not BreakerState.OPEN,
            breaker=state,
            index=await self._index.index_info(),
        )
