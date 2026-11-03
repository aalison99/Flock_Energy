from datetime import UTC, datetime, timedelta

from app.core.cache import InMemoryTTLCache
from tests.support.fake_clock import FakeClock

T0 = datetime(2026, 11, 4, tzinfo=UTC)


def _make(max_entries: int = 3) -> tuple[InMemoryTTLCache, FakeClock]:
    clock = FakeClock(T0)
    return InMemoryTTLCache(clock, max_entries), clock


def test_miss_is_none() -> None:
    cache, _ = _make()
    assert cache.get("a") is None


def test_set_get_records_times() -> None:
    cache, _ = _make()
    cache.set("a", [1], 60)
    entry = cache.get("a")
    assert entry is not None
    assert (entry.value, entry.stored_at, entry.expires_at) == ([1], T0, T0 + timedelta(seconds=60))


def test_expired_entry_is_still_returned() -> None:
    cache, clock = _make()
    cache.set("a", "v", 60)
    clock.advance(61)
    entry = cache.get("a")
    assert entry is not None and entry.value == "v"
    assert entry.expires_at < clock.now()


def test_overwrite_refreshes_times() -> None:
    cache, clock = _make()
    cache.set("a", 1, 10)
    clock.advance(5)
    cache.set("a", 2, 10)
    entry = cache.get("a")
    assert entry is not None and entry.value == 2 and entry.stored_at == clock.now()


def test_lru_evicts_oldest() -> None:
    cache, _ = _make(max_entries=3)
    for key in "abcd":
        cache.set(key, key, 60)
    assert cache.get("a") is None
    assert [cache.get(k) is not None for k in "bcd"] == [True, True, True]


def test_get_refreshes_recency() -> None:
    cache, _ = _make(max_entries=3)
    for key in "abc":
        cache.set(key, key, 60)
    cache.get("a")
    cache.set("d", "d", 60)
    assert cache.get("b") is None
    assert cache.get("a") is not None


def test_set_refreshes_recency() -> None:
    cache, _ = _make(max_entries=3)
    for key in "abc":
        cache.set(key, key, 60)
    cache.set("a", "a2", 60)
    cache.set("d", "d", 60)
    assert cache.get("b") is None
    assert cache.get("a") is not None


def test_invalidate_prefix() -> None:
    cache, _ = _make(max_entries=10)
    for key in ("portal:a:1", "portal:a:2", "portal:b:1", "other"):
        cache.set(key, 1, 60)
    cache.invalidate("portal:a:")
    assert [
        cache.get(k) is not None for k in ("portal:a:1", "portal:a:2", "portal:b:1", "other")
    ] == [
        False,
        False,
        True,
        True,
    ]


def test_peek_returns_entry_without_touching_recency() -> None:
    cache, _ = _make(max_entries=3)
    for key in "abc":
        cache.set(key, key, 60)
    peeked = cache.peek("a")
    assert peeked is not None and peeked.value == "a"
    assert cache.peek("zzz") is None
    cache.set("d", "d", 60)
    assert cache.peek("a") is None  # "a" was still the oldest, so it was evicted
