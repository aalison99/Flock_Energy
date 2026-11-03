import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.domain.exceptions import (
    NotFoundError,
    UpstreamAuthError,
    UpstreamProtocolError,
    UpstreamUnavailableError,
    ValidationError,
)
from app.portal.breaker import BreakerState, CircuitBreaker
from app.portal.fake import FakePortalClient
from app.portal.retrying import RetryingClient, RetryPolicy
from tests.support.fake_clock import FakeClock, FakeSleeper

FIXTURES = Path(__file__).parents[2] / "fixtures" / "portal"
POLICY = RetryPolicy(attempts=3, base_delay_s=1.0, max_delay_s=3.0, retry_after_cap_s=10.0)

pytestmark = pytest.mark.anyio


class Rig:
    def __init__(self, *, policy: RetryPolicy = POLICY, threshold: int = 100, jitter: float = 1.0):
        self.clock = FakeClock(datetime(2026, 11, 4, tzinfo=UTC))
        self.sleeper = FakeSleeper(self.clock)
        self.fake = FakePortalClient(FIXTURES)
        self.breaker = CircuitBreaker(failure_threshold=threshold, reset_s=30, clock=self.clock)
        self.client = RetryingClient(
            self.fake,
            policy=policy,
            breaker=self.breaker,
            sleep=self.sleeper,
            jitter=lambda: jitter,
        )

    def calls(self, method: str) -> int:
        return sum(1 for m, _ in self.fake.calls if m == method)


def _down(retry_after: int | None = None) -> UpstreamUnavailableError:
    return UpstreamUnavailableError("secret-detail-xyz", retry_after_s=retry_after)


async def test_success_passes_through() -> None:
    rig = Rig()
    assert (await rig.client.get_meter("J100000")).meter_id == "J100000"
    assert rig.sleeper.delays == []


async def test_retry_then_success() -> None:
    rig = Rig()
    rig.fake.fail("get_meter", _down(), times=2)
    assert (await rig.client.get_meter("J100000")).meter_id == "J100000"
    assert rig.calls("get_meter") == 3
    assert rig.breaker.state is BreakerState.CLOSED


async def test_gives_up_with_last_error() -> None:
    rig = Rig()
    errors = [_down(), _down(), _down()]
    for e in errors:
        rig.fake.fail("get_meter", e)
    with pytest.raises(UpstreamUnavailableError) as info:
        await rig.client.get_meter("J100000")
    assert info.value is errors[2]
    assert rig.calls("get_meter") == 3


@pytest.mark.parametrize(("jitter", "expected"), [(1.0, [1.0, 2.0]), (0.0, [0.5, 1.0])])
async def test_delays_follow_formula(jitter: float, expected: list[float]) -> None:
    rig = Rig(jitter=jitter)
    rig.fake.fail("get_meter", _down(), times=5)
    with pytest.raises(UpstreamUnavailableError):
        await rig.client.get_meter("J100000")
    assert rig.sleeper.delays == expected


async def test_delay_capped_at_max() -> None:
    policy = RetryPolicy(attempts=4, base_delay_s=1.0, max_delay_s=3.0, retry_after_cap_s=10.0)
    rig = Rig(policy=policy, jitter=1.0)
    rig.fake.fail("get_meter", _down(), times=5)
    with pytest.raises(UpstreamUnavailableError):
        await rig.client.get_meter("J100000")
    assert rig.sleeper.delays == [1.0, 2.0, 3.0]


async def test_retry_after_respected() -> None:
    rig = Rig()
    rig.fake.fail("get_meter", _down(retry_after=7))
    await rig.client.get_meter("J100000")
    assert rig.sleeper.delays == [7]


async def test_retry_after_over_cap_not_retried() -> None:
    rig = Rig()
    err = _down(retry_after=11)
    rig.fake.fail("get_meter", err)
    with pytest.raises(UpstreamUnavailableError) as info:
        await rig.client.get_meter("J100000")
    assert info.value is err
    assert rig.calls("get_meter") == 1
    assert rig.sleeper.delays == []


@pytest.mark.parametrize(
    "error",
    [
        NotFoundError("x"),
        UpstreamProtocolError("x"),
        ValidationError("x"),
        UpstreamAuthError("x"),
    ],
)
async def test_non_retryable_errors(error: Exception) -> None:
    rig = Rig()
    rig.fake.fail("get_meter", error)
    with pytest.raises(type(error)):
        await rig.client.get_meter("J100000")
    assert rig.calls("get_meter") == 1
    assert rig.sleeper.delays == []


async def test_auth_counts_toward_breaker_not_found_does_not() -> None:
    rig = Rig(threshold=2)
    rig.fake.fail("get_meter", NotFoundError("x"), times=5)
    for _ in range(3):
        with pytest.raises(NotFoundError):
            await rig.client.get_meter("J100000")
    assert rig.breaker.state is BreakerState.CLOSED

    rig = Rig(threshold=2)
    rig.fake.fail("get_meter", UpstreamAuthError("x"), times=5)
    for _ in range(2):
        with pytest.raises(UpstreamAuthError):
            await rig.client.get_meter("J100000")
    assert rig.breaker.state is BreakerState.OPEN
    with pytest.raises(UpstreamUnavailableError, match="circuit open"):
        await rig.client.get_meter("J100000")
    assert rig.calls("get_meter") == 2


async def test_not_found_resets_failure_streak() -> None:
    rig = Rig(threshold=2, policy=RetryPolicy(1, 1.0, 1.0, 10.0))
    rig.fake.fail("get_meter", _down())
    rig.fake.fail("get_meter", NotFoundError("x"), on_call=2)
    rig.fake.fail("get_meter", _down(), on_call=3)
    for expected in (UpstreamUnavailableError, NotFoundError, UpstreamUnavailableError):
        with pytest.raises(expected):
            await rig.client.get_meter("J100000")
    assert rig.breaker.state is BreakerState.CLOSED


async def test_breaker_opening_mid_loop_stops_retries() -> None:
    policy = RetryPolicy(attempts=5, base_delay_s=1.0, max_delay_s=3.0, retry_after_cap_s=10.0)
    rig = Rig(policy=policy, threshold=2)
    rig.fake.fail("get_meter", _down(), times=10)
    with pytest.raises(UpstreamUnavailableError, match="circuit open"):
        await rig.client.get_meter("J100000")
    assert rig.calls("get_meter") == 2
    assert len(rig.sleeper.delays) == 2  # waited before attempt 2 and before the refused 3rd


async def test_open_breaker_blocks_every_method_without_calling_inner() -> None:
    rig = Rig(threshold=1, policy=RetryPolicy(1, 1.0, 1.0, 10.0))
    rig.fake.fail("list_transformers", _down())
    with pytest.raises(UpstreamUnavailableError):
        await rig.client.list_transformers(1)
    with pytest.raises(UpstreamUnavailableError, match="circuit open"):
        await rig.client.bulk_export()
    assert rig.calls("bulk_export") == 0


async def test_all_methods_delegate() -> None:
    rig = Rig()
    got = [
        await rig.client.list_meters(2, "x"),
        await rig.client.get_meter("J100000"),
        await rig.client.get_geo("J100000"),
        await rig.client.get_readings("J100000"),
        await rig.client.list_transformers(1),
        await rig.client.bulk_export(),
    ]
    assert rig.fake.calls == [
        ("list_meters", (2, "x")),
        ("get_meter", ("J100000",)),
        ("get_geo", ("J100000",)),
        ("get_readings", ("J100000", None, None)),
        ("list_transformers", (1,)),
        ("bulk_export", ()),
    ]
    ref = FakePortalClient(FIXTURES)
    assert got == [
        await ref.list_meters(2, "x"),
        await ref.get_meter("J100000"),
        await ref.get_geo("J100000"),
        await ref.get_readings("J100000"),
        await ref.list_transformers(1),
        await ref.bulk_export(),
    ]
    await rig.client.aclose()
    assert rig.fake.closed


async def _half_open(rig: Rig) -> None:
    rig.breaker.record_failure(rig.breaker.before_call())  # threshold is 1 in these tests
    rig.clock.advance(30)
    assert rig.breaker.state is BreakerState.HALF_OPEN


def _one_shot() -> RetryPolicy:
    return RetryPolicy(1, 1.0, 1.0, 10.0)


async def test_cancelled_trial_releases_the_slot() -> None:
    rig = Rig(threshold=1, policy=_one_shot())
    await _half_open(rig)
    rig.fake.fail("get_meter", asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        await rig.client.get_meter("J100000")
    assert rig.breaker.state is BreakerState.HALF_OPEN
    assert (await rig.client.get_meter("J100000")).meter_id == "J100000"
    assert rig.breaker.state is BreakerState.CLOSED


async def test_unexpected_error_trial_reopens_with_fresh_timer() -> None:
    rig = Rig(threshold=1, policy=_one_shot())
    await _half_open(rig)
    rig.fake.fail("get_meter", RuntimeError("bug"))
    with pytest.raises(RuntimeError):
        await rig.client.get_meter("J100000")
    assert rig.breaker.state is BreakerState.OPEN
    rig.clock.advance(29)
    assert rig.breaker.state is BreakerState.OPEN
    rig.clock.advance(1)
    assert rig.breaker.state is BreakerState.HALF_OPEN


async def test_not_found_trial_closes_the_breaker() -> None:
    rig = Rig(threshold=1, policy=_one_shot())
    await _half_open(rig)
    rig.fake.fail("get_meter", NotFoundError("x"))
    with pytest.raises(NotFoundError):
        await rig.client.get_meter("J100000")
    assert rig.breaker.state is BreakerState.CLOSED


async def test_retry_across_half_open_trial() -> None:
    rig = Rig(threshold=1, policy=RetryPolicy(3, 1.0, 1.0, 10.0), jitter=1.0)
    await _half_open(rig)
    rig.fake.fail("get_meter", _down())  # the trial fails, re-opening the circuit
    with pytest.raises(UpstreamUnavailableError, match="circuit open"):
        await rig.client.get_meter("J100000")
    assert rig.calls("get_meter") == 1


async def test_warning_log_has_no_exception_text(caplog: pytest.LogCaptureFixture) -> None:
    rig = Rig()
    rig.fake.fail("get_meter", _down())
    with caplog.at_level(logging.WARNING, logger="app.portal.retrying"):
        await rig.client.get_meter("J100000")
    assert [r.getMessage() for r in caplog.records] == [
        "portal call get_meter failed (UpstreamUnavailableError); retry 1/2 in 1.00s"
    ]
    assert "secret-detail-xyz" not in caplog.text
