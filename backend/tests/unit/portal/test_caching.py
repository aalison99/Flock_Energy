import logging
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from app.core.cache import InMemoryTTLCache
from app.domain.exceptions import NotFoundError, UpstreamAuthError, UpstreamUnavailableError
from app.portal.caching import CachingClient, TtlPolicy
from app.portal.fake import FakePortalClient
from app.portal.interfaces import cache_key
from tests.support.fake_clock import FakeClock

FIXTURES = Path(__file__).parents[2] / "fixtures" / "portal"
T0 = datetime(2026, 11, 4, tzinfo=UTC)
TTLS = TtlPolicy(static_s=100.0, readings_s=10.0)

pytestmark = pytest.mark.anyio


class Rig:
    def __init__(self) -> None:
        self.clock = FakeClock(T0)
        self.fake = FakePortalClient(FIXTURES)
        self.cache = InMemoryTTLCache(self.clock, 100)
        self.client = CachingClient(self.fake, cache=self.cache, ttls=TTLS, clock=self.clock)

    def calls(self, method: str) -> int:
        return sum(1 for m, _ in self.fake.calls if m == method)


async def test_hit_within_ttl_calls_inner_once() -> None:
    rig = Rig()
    first = await rig.client.get_meter("J100000")
    rig.clock.advance(100)  # exactly at expiry is still fresh
    assert await rig.client.get_meter("J100000") == first
    assert rig.calls("get_meter") == 1


async def test_miss_after_ttl() -> None:
    rig = Rig()
    await rig.client.get_meter("J100000")
    rig.clock.advance(101)
    await rig.client.get_meter("J100000")
    assert rig.calls("get_meter") == 2


@pytest.mark.parametrize(
    ("method", "args"),
    [
        ("list_meters", (1, "x")),
        ("get_meter", ("J100000",)),
        ("get_geo", ("J100000",)),
        ("list_transformers", (1,)),
    ],
)
async def test_static_methods_use_static_ttl(method: str, args: tuple[object, ...]) -> None:
    rig = Rig()
    await getattr(rig.client, method)(*args)
    rig.clock.advance(50)
    await getattr(rig.client, method)(*args)
    assert rig.calls(method) == 1
    freshness = rig.client.freshness(method, *args)
    assert freshness is not None
    assert freshness.expires_at == T0 + timedelta(seconds=100)


async def test_readings_use_readings_ttl() -> None:
    rig = Rig()
    await rig.client.get_readings("J100000")
    rig.clock.advance(11)
    await rig.client.get_readings("J100000")
    assert rig.calls("get_readings") == 2


async def test_none_geo_is_cached() -> None:
    rig = Rig()

    class NoGeo(FakePortalClient):
        async def get_geo(self, meter_id: str) -> None:
            self._enter("get_geo", meter_id)

    rig.fake = NoGeo(FIXTURES)
    rig.client = CachingClient(rig.fake, cache=rig.cache, ttls=TTLS, clock=rig.clock)
    assert await rig.client.get_geo("J100000") is None
    assert await rig.client.get_geo("J100000") is None
    assert rig.calls("get_geo") == 1


async def test_stale_on_error_returns_old_value_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    rig = Rig()
    first = await rig.client.get_meter("J100000")
    rig.clock.advance(500)
    rig.fake.fail("get_meter", UpstreamUnavailableError("down-detail"))
    with caplog.at_level(logging.WARNING, logger="app.portal.caching"):
        assert await rig.client.get_meter("J100000") == first
    assert [r.getMessage() for r in caplog.records] == ["serving stale get_meter"]
    freshness = rig.client.freshness("get_meter", "J100000")
    assert freshness is not None and freshness.stale


async def test_no_cached_entry_reraises() -> None:
    rig = Rig()
    rig.fake.fail("get_meter", UpstreamUnavailableError("down"))
    with pytest.raises(UpstreamUnavailableError):
        await rig.client.get_meter("J100000")


@pytest.mark.parametrize("error", [NotFoundError("x"), UpstreamAuthError("x")])
async def test_other_errors_reraise_even_with_stale_entry(error: Exception) -> None:
    rig = Rig()
    await rig.client.get_meter("J100000")
    rig.clock.advance(500)
    rig.fake.fail("get_meter", error)
    with pytest.raises(type(error)):
        await rig.client.get_meter("J100000")


async def test_errors_are_not_cached() -> None:
    rig = Rig()
    with pytest.raises(NotFoundError):
        await rig.client.get_meter("J999999")
    assert rig.client.freshness("get_meter", "J999999") is None
    with pytest.raises(NotFoundError):
        await rig.client.get_meter("J999999")
    assert rig.calls("get_meter") == 2


async def test_bulk_export_never_cached() -> None:
    rig = Rig()
    await rig.client.bulk_export()
    await rig.client.bulk_export()
    assert rig.calls("bulk_export") == 2
    assert len(rig.cache._entries) == 0


async def test_bulk_export_errors_propagate_without_stale() -> None:
    rig = Rig()
    await rig.client.bulk_export()
    rig.fake.fail("bulk_export", UpstreamUnavailableError("down"))
    with pytest.raises(UpstreamUnavailableError):
        await rig.client.bulk_export()


async def test_aclose_delegates() -> None:
    rig = Rig()
    await rig.client.aclose()
    assert rig.fake.closed


async def test_mutating_returned_list_does_not_touch_cache() -> None:
    rig = Rig()
    first = await rig.client.get_readings("J100000")
    expected = len(first)
    assert expected > 0
    first.clear()
    again = await rig.client.get_readings("J100000")
    assert len(again) == expected
    again.append(again[0])
    assert len(await rig.client.get_readings("J100000")) == expected
    assert rig.calls("get_readings") == 1


async def test_freshness_before_and_after_expiry() -> None:
    rig = Rig()
    assert rig.client.freshness("get_meter", "J100000") is None
    await rig.client.get_meter("J100000")
    fresh = rig.client.freshness("get_meter", "J100000")
    assert fresh is not None
    assert (fresh.fetched_at, fresh.stale) == (T0, False)
    rig.clock.advance(101)
    stale = rig.client.freshness("get_meter", "J100000")
    assert stale is not None and stale.stale and stale.expires_at == fresh.expires_at


async def test_distinct_keys_for_distinct_args() -> None:
    rig = Rig()
    await rig.client.list_meters(1)
    await rig.client.list_meters(2)
    await rig.client.list_meters(1, "0001")
    await rig.client.get_readings("J100000")
    await rig.client.get_readings("J100000", date(2025, 1, 1))
    await rig.client.get_readings("J100000", None, date(2025, 1, 1))
    assert rig.calls("list_meters") == 3
    assert rig.calls("get_readings") == 3


def test_cache_key_normalisation() -> None:
    assert cache_key("list_meters", 1, None) == cache_key("list_meters", 1, "  ")
    assert cache_key("list_meters", 1, " Ab ") == "portal:list_meters:1|Ab"
    assert cache_key("list_meters", 1, "ab") != cache_key("list_meters", 1, "AB")
    assert (
        cache_key("get_readings", "M", None, date(2025, 1, 2))
        == "portal:get_readings:M|-|2025-01-02"
    )
    assert cache_key("get_readings", "M", date(2025, 1, 2), None) != cache_key(
        "get_readings", "M", None, date(2025, 1, 2)
    )


def test_cache_key_escapes_separators() -> None:
    assert cache_key("get_readings", "a|b", "c") != cache_key("get_readings", "a", "b|c")
    assert cache_key("get_meter", "a\\") != cache_key("get_meter", "a", "")
    assert cache_key("get_meter", "a|b") == "portal:get_meter:a\\|b"


def test_cache_key_does_not_strip_ids() -> None:
    assert cache_key("get_meter", " J1") != cache_key("get_meter", "J1")


async def test_inner_receives_the_normalised_query() -> None:
    rig = Rig()
    await rig.client.list_meters(1, "  0001 ")
    await rig.client.list_meters(1, "0001")
    await rig.client.list_meters(1, None)
    await rig.client.list_meters(1, "   ")
    assert rig.fake.calls == [("list_meters", (1, "0001")), ("list_meters", (1, ""))]


async def test_freshness_does_not_change_lru_order() -> None:
    rig = Rig()
    rig.cache = InMemoryTTLCache(rig.clock, 2)
    rig.client = CachingClient(rig.fake, cache=rig.cache, ttls=TTLS, clock=rig.clock)
    await rig.client.get_meter("J100000")
    await rig.client.get_meter("J100001")
    assert rig.client.freshness("get_meter", "J100000") is not None  # must not refresh it
    await rig.client.get_meter("J100002")  # evicts the oldest, J100000
    assert rig.client.freshness("get_meter", "J100000") is None
    assert rig.client.freshness("get_meter", "J100001") is not None
