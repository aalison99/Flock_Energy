"""The PortalClient Protocol: the only surface the rest of the app sees of the legacy portal."""

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from app.domain.models import GeoPoint, Meter, Reading, Transformer


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
