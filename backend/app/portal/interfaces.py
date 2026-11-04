"""The PortalClient Protocol: the only surface the rest of the app sees of the legacy portal."""

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Protocol

from app.domain.models import GeoPoint, Meter, Reading, Transformer


class BreakerState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True, slots=True)
class PortalPage[T]:
    """One page of portal results with the portal's own paging numbers."""

    items: tuple[T, ...]
    total: int
    page: int
    page_size: int


class PortalClient(Protocol):
    """Async access to the portal's data.

    The only exceptions that may escape any method are, from `app.domain.exceptions`:
    NotFoundError, UpstreamAuthError, UpstreamUnavailableError and UpstreamProtocolError.
    """

    async def list_meters(self, page: int, query: str | None = None) -> PortalPage[Meter]: ...

    async def get_meter(self, meter_id: str) -> Meter:
        """Nameplate and hierarchy; geo is None."""
        ...

    async def get_geo(self, meter_id: str) -> GeoPoint | None: ...

    async def get_readings(
        self, meter_id: str, start: date | None = None, end: date | None = None
    ) -> list[Reading]:
        """Ascending by time; start and end are inclusive calendar days."""
        ...

    async def list_transformers(self, page: int) -> PortalPage[Transformer]: ...

    async def bulk_export(self) -> list[Meter]:
        """Every meter, with full records."""
        ...

    async def aclose(self) -> None: ...


class BreakerStateReader(Protocol):
    """Read-only view of the portal circuit breaker (for health checks)."""

    @property
    def state(self) -> BreakerState: ...


@dataclass(frozen=True)
class Freshness:
    """When a cached portal answer was fetched, when it expires, and whether it already has."""

    fetched_at: datetime
    expires_at: datetime
    stale: bool


class FreshnessReader(Protocol):
    def freshness(self, method: str, *args: object) -> Freshness | None:
        """Metadata of the currently cached entry for that call, if any."""
        ...


def cache_key(method: str, *args: object) -> str:
    """Stable cache key: `portal:<method>:<normalised args joined by |>`.

    None -> "-" and dates/datetimes -> ISO; `|` and `\\` inside parts are backslash-escaped.
    The list_meters query is normalised with `normalise_query` (None -> "", stripped) and is
    not lower-cased: the portal ignores case, but keys stay honest. Other strings are kept as is.
    """
    if method == "list_meters" and len(args) > 1:
        args = (*args[:1], normalise_query(args[1]), *args[2:])
    return "portal:" + method + ":" + "|".join(_norm(a) for a in args)


def normalise_query(query: object) -> str:
    """The search query as sent to the portal and as keyed: None -> "", surrounding blanks gone."""
    return query.strip() if isinstance(query, str) else ""


def _norm(arg: object) -> str:
    if arg is None:
        text = "-"
    elif isinstance(arg, date):  # datetime is a date subclass
        text = arg.isoformat()
    elif isinstance(arg, str):
        text = arg
    else:
        text = repr(arg)
    return text.replace("\\", "\\\\").replace("|", "\\|")
