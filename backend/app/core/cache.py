"""In-memory TTL cache with LRU eviction; the only concrete Cache (wired in app.core.deps).

Not thread-safe by design: the app runs on a single event loop and no method awaits.
`get` returns expired entries too; callers decide whether staleness is acceptable.
"""

from collections import OrderedDict
from datetime import timedelta

from app.core.interfaces import CacheEntry, Clock


class InMemoryTTLCache:
    """Implements Cache: bounded by `max_entries`, evicting the least recently used."""

    def __init__(self, clock: Clock, max_entries: int) -> None:
        self._clock = clock
        self._max = max_entries
        self._entries: OrderedDict[str, CacheEntry] = OrderedDict()

    def get(self, key: str) -> CacheEntry | None:
        entry = self._entries.get(key)
        if entry is not None:
            self._entries.move_to_end(key)
        return entry

    def peek(self, key: str) -> CacheEntry | None:
        return self._entries.get(key)

    def set(self, key: str, value: object, ttl_s: float) -> None:
        now = self._clock.now()
        self._entries[key] = CacheEntry(value, now, now + timedelta(seconds=ttl_s))
        self._entries.move_to_end(key)
        while len(self._entries) > self._max:
            self._entries.popitem(last=False)

    def invalidate(self, prefix: str) -> None:
        for key in [k for k in self._entries if k.startswith(prefix)]:
            del self._entries[key]
