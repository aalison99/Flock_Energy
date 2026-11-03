"""Circuit breaker: stops hammering a portal that keeps failing, then probes with one call."""

import math
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.core.interfaces import Clock
from app.domain.exceptions import UpstreamUnavailableError


class BreakerState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True)
class Permit:
    """Issued to every admitted call; only the current half-open trial's permit can settle an
    open circuit (`generation` counts how many times the circuit has opened)."""

    is_trial: bool
    generation: int


class CircuitBreaker:
    """CLOSED -> OPEN after N consecutive failures; after reset_s one trial call (HALF_OPEN).

    Single event loop: methods are synchronous and never await, so no locking is needed.
    """

    def __init__(self, *, failure_threshold: int, reset_s: float, clock: Clock) -> None:
        self._threshold = failure_threshold
        self._reset_s = reset_s
        self._clock = clock
        self._failures = 0
        self._opened_at: datetime | None = None
        self._trial_in_flight = False
        self._generation = 0

    @property
    def state(self) -> BreakerState:
        if self._opened_at is None:
            return BreakerState.CLOSED
        if self._remaining() > 0:
            return BreakerState.OPEN
        return BreakerState.HALF_OPEN

    def _remaining(self) -> float:
        assert self._opened_at is not None
        return self._reset_s - (self._clock.now() - self._opened_at).total_seconds()

    def before_call(self) -> Permit:
        """Admit a call and return its permit; raise UpstreamUnavailableError if refused."""
        state = self.state
        if state is BreakerState.CLOSED:
            return Permit(is_trial=False, generation=self._generation)
        if state is BreakerState.HALF_OPEN and not self._trial_in_flight:
            self._trial_in_flight = True
            return Permit(is_trial=True, generation=self._generation)
        retry_after = max(1, math.ceil(self._remaining())) if state is BreakerState.OPEN else 1
        raise UpstreamUnavailableError("portal circuit open", retry_after_s=retry_after)

    def _is_current_trial(self, permit: Permit) -> bool:
        return permit.is_trial and permit.generation == self._generation and self._trial_in_flight

    def release_trial(self, permit: Permit) -> None:
        """Free the half-open trial slot without counting an outcome (e.g. a cancelled call)."""
        if self._is_current_trial(permit):
            self._trial_in_flight = False

    def record_success(self, permit: Permit) -> None:
        """CLOSED: resets the streak. Once opened, only the current trial's permit can close."""
        if self._opened_at is None:
            self._failures = 0
        elif self._is_current_trial(permit):
            self._failures = 0
            self._opened_at = None
            self._trial_in_flight = False

    def record_failure(self, permit: Permit) -> None:
        """CLOSED: counts toward the threshold. Once opened, only the current trial reopens."""
        if self._opened_at is None:
            self._failures += 1
            if self._failures >= self._threshold:
                self._open()
        elif self._is_current_trial(permit):
            self._open()  # failed trial: restart the timer

    def _open(self) -> None:
        self._opened_at = self._clock.now()
        self._generation += 1
        self._trial_in_flight = False
