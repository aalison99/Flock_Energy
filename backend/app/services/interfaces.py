"""Service-layer Protocols: what the meter service needs from a catalog of meters."""

from dataclasses import dataclass
from typing import Protocol

from app.domain.models import Meter, PageResult


@dataclass(frozen=True)
class MeterFilters:
    """Search filters; M6 adds more fields (a live catalog rejects any it cannot serve)."""

    q: str | None = None


class MeterCatalog(Protocol):
    async def search(self, filters: MeterFilters, page: int, page_size: int) -> PageResult[Meter]:
        """One page of meters matching the filters, with the total match count."""
        ...

    async def get(self, meter_id: str) -> Meter:
        """Raises NotFoundError for an unknown meter."""
        ...
