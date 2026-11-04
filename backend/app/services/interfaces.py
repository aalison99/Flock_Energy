"""Service-layer Protocols: what the meter service needs from a catalog of meters."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal, Protocol

from app.domain.models import InstallStatus, InstallType, Meter, PageResult, PhaseType
from app.services.results import IndexInfo


class MeterSort(StrEnum):
    """Sort keys for meter lists; ties are always broken by meter_id."""

    METER_ID = "meter_id"
    METER_ID_DESC = "-meter_id"
    MAKE = "make"
    STATUS = "status"


class FacetField(StrEnum):
    """Meter attributes that can be counted."""

    STATUS = "status"
    MAKE = "make"
    PHASE = "phase"
    INSTALL_TYPE = "install_type"
    DT = "dt"


@dataclass(frozen=True)
class MeterFilters:
    """Combinable search filters (all must match). A live catalog serves only `q`.

    A hierarchy code matches the code at that level wherever it occurs.
    """

    q: str | None = None  # case-insensitive substring of meter_id or serial_no
    status: tuple[InstallStatus, ...] = ()  # any-of
    make: tuple[str, ...] = ()  # any-of, exact match
    phase: PhaseType | None = None
    install_type: InstallType | None = None
    dt: str | None = None  # the meter's own dt_code
    feeder: str | None = None
    substation: str | None = None
    subdivision: str | None = None
    division: str | None = None
    circle: str | None = None
    zone: str | None = None
    has_geo: bool | None = None
    sort: MeterSort = MeterSort.METER_ID


@dataclass(frozen=True)
class CatalogHit:
    """One meter and where it came from (`synced_at` is set only for the index)."""

    meter: Meter
    source: Literal["portal", "index"]
    synced_at: datetime | None


class MeterCatalog(Protocol):
    async def search(self, filters: MeterFilters, page: int, page_size: int) -> PageResult[Meter]:
        """One page of meters matching the filters, with the total match count."""
        ...

    async def get(self, meter_id: str) -> CatalogHit:
        """Raises NotFoundError for an unknown meter."""
        ...

    async def facets(
        self, filters: MeterFilters, fields: Sequence[FacetField]
    ) -> dict[FacetField, dict[str, int]]:
        """Per field, matching meters per value; each field ignores its own filter."""
        ...


class IndexStatusReader(Protocol):
    """Read-only view of the local index (for the readiness probe)."""

    async def index_info(self) -> IndexInfo: ...
