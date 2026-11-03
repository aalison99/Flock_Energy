from datetime import UTC, datetime

import pytest

from app.domain.exceptions import UpstreamUnavailableError
from app.portal.breaker import BreakerState, CircuitBreaker, Permit
from tests.support.fake_clock import FakeClock


def _make(threshold: int = 3, reset_s: float = 30.0) -> tuple[CircuitBreaker, FakeClock]:
    clock = FakeClock(datetime(2026, 11, 4, tzinfo=UTC))
    return CircuitBreaker(failure_threshold=threshold, reset_s=reset_s, clock=clock), clock


def _fail(breaker: CircuitBreaker, n: int = 1) -> None:
    for _ in range(n):
        breaker.record_failure(breaker.before_call())


def _open(breaker: CircuitBreaker, n: int = 3) -> None:
    _fail(breaker, n)


def test_starts_closed_and_allows_calls() -> None:
    breaker, _ = _make()
    assert breaker.state is BreakerState.CLOSED
    assert breaker.before_call().is_trial is False


def test_opens_at_threshold_not_before() -> None:
    breaker, _ = _make(threshold=3)
    _fail(breaker, 2)
    assert breaker.state is BreakerState.CLOSED
    _fail(breaker)
    assert breaker.state is BreakerState.OPEN


def test_success_resets_failure_count() -> None:
    breaker, _ = _make(threshold=3)
    _fail(breaker, 2)
    breaker.record_success(breaker.before_call())
    _fail(breaker, 2)
    assert breaker.state is BreakerState.CLOSED


def test_open_fast_fails_with_ceil_remaining() -> None:
    breaker, clock = _make(reset_s=30.0)
    _open(breaker)
    clock.advance(10.5)
    with pytest.raises(UpstreamUnavailableError) as info:
        breaker.before_call()
    assert info.value.message == "portal circuit open"
    assert info.value.retry_after_s == 20  # ceil(19.5)


def test_half_open_after_reset() -> None:
    breaker, clock = _make(reset_s=30.0)
    _open(breaker)
    clock.advance(29.9)
    assert breaker.state is BreakerState.OPEN
    clock.advance(0.1)
    assert breaker.state is BreakerState.HALF_OPEN


def test_half_open_allows_exactly_one_trial() -> None:
    breaker, clock = _make()
    _open(breaker)
    clock.advance(30)
    assert breaker.before_call().is_trial is True
    with pytest.raises(UpstreamUnavailableError):
        breaker.before_call()  # concurrent extra
    assert breaker.state is BreakerState.HALF_OPEN


def test_trial_success_closes() -> None:
    breaker, clock = _make()
    _open(breaker)
    clock.advance(30)
    breaker.record_success(breaker.before_call())
    assert breaker.state is BreakerState.CLOSED
    breaker.before_call()
    breaker.before_call()


def test_trial_failure_reopens_with_fresh_timer() -> None:
    breaker, clock = _make(reset_s=30.0)
    _open(breaker)
    clock.advance(30)
    breaker.record_failure(breaker.before_call())
    assert breaker.state is BreakerState.OPEN
    clock.advance(29)
    assert breaker.state is BreakerState.OPEN
    with pytest.raises(UpstreamUnavailableError) as info:
        breaker.before_call()
    assert info.value.retry_after_s == 1
    clock.advance(1)
    assert breaker.state is BreakerState.HALF_OPEN
    assert breaker.before_call().is_trial  # a new trial is allowed


def test_release_trial_allows_a_new_trial_without_counting() -> None:
    breaker, clock = _make()
    _open(breaker)
    clock.advance(30)
    breaker.release_trial(breaker.before_call())
    assert breaker.state is BreakerState.HALF_OPEN
    assert breaker.before_call().is_trial  # a fresh trial is admitted


def test_release_trial_ignores_non_trial_and_stale_permits() -> None:
    breaker, clock = _make()
    straggler = breaker.before_call()
    _open(breaker)
    clock.advance(30)
    trial = breaker.before_call()
    breaker.release_trial(straggler)
    with pytest.raises(UpstreamUnavailableError):
        breaker.before_call()  # the trial slot is still held
    breaker.release_trial(trial)
    assert breaker.before_call().is_trial


def test_late_result_while_open_is_ignored() -> None:
    breaker, clock = _make(reset_s=30.0)
    straggler = breaker.before_call()
    _open(breaker)
    clock.advance(10)
    breaker.record_failure(straggler)
    clock.advance(20)
    assert breaker.state is BreakerState.HALF_OPEN  # timer not restarted

    breaker, _ = _make()
    straggler = breaker.before_call()
    _open(breaker)
    breaker.record_success(straggler)
    assert breaker.state is BreakerState.OPEN


def test_straggler_success_during_trial_does_not_close() -> None:
    breaker, clock = _make()
    a = breaker.before_call()  # admitted while CLOSED
    _open(breaker)
    clock.advance(30)
    b = breaker.before_call()  # the trial
    assert (a.is_trial, b.is_trial) == (False, True)
    breaker.record_success(a)
    assert breaker.state is BreakerState.HALF_OPEN
    with pytest.raises(UpstreamUnavailableError):
        breaker.before_call()  # trial B still in flight
    breaker.record_failure(b)
    assert breaker.state is BreakerState.OPEN


def test_straggler_failure_during_trial_is_ignored() -> None:
    breaker, clock = _make()
    a = breaker.before_call()
    _open(breaker)
    clock.advance(30)
    b = breaker.before_call()
    breaker.record_failure(a)
    assert breaker.state is BreakerState.HALF_OPEN
    breaker.record_success(b)
    assert breaker.state is BreakerState.CLOSED


def test_stale_trial_permit_from_previous_generation_is_ignored() -> None:
    breaker, clock = _make()
    _open(breaker)
    clock.advance(30)
    old_trial = breaker.before_call()
    breaker.release_trial(old_trial)
    breaker.record_failure(breaker.before_call())  # new trial fails: generation moves on
    clock.advance(30)
    new_trial = breaker.before_call()
    assert new_trial.generation != old_trial.generation
    breaker.record_success(old_trial)
    assert breaker.state is BreakerState.HALF_OPEN
    breaker.record_failure(old_trial)
    assert breaker.state is BreakerState.HALF_OPEN
    breaker.record_success(new_trial)
    assert breaker.state is BreakerState.CLOSED


def test_permit_is_frozen() -> None:
    permit = Permit(is_trial=False, generation=0)
    with pytest.raises(AttributeError):
        permit.is_trial = True  # type: ignore[misc]
