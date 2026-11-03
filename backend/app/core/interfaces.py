"""Core Protocols (Clock, Cache) that services depend on instead of concrete classes."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    """Source of the current time; always timezone-aware."""

    def now(self) -> datetime: ...


@dataclass(frozen=True)
class CacheEntry:
    """A cached value with its storage and expiry instants."""

    value: object
    stored_at: datetime
    expires_at: datetime


class Cache(Protocol):
    """Key/value cache with TTL and prefix invalidation."""

    def get(self, key: str) -> CacheEntry | None: ...

    def peek(self, key: str) -> CacheEntry | None:
        """Like get, but does not change eviction order."""
        ...

    def set(self, key: str, value: object, ttl_s: float) -> None: ...

    def invalidate(self, prefix: str) -> None: ...
