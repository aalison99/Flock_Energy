"""Domain models shared across layers: meters, hierarchy, readings, transformers, paging."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


@dataclass(frozen=True)
class PageResult[T]:
    """One slice of items plus the total number of matching items."""

    items: Sequence[T]
    total: int


class PhaseType(StrEnum):
    SINGLE = "single"
    THREE = "three"
    UNKNOWN = "unknown"


class InstallStatus(StrEnum):
    INSTALLED = "installed"
    FAULTY = "faulty"
    DECOMMISSIONED = "decommissioned"
    UNKNOWN = "unknown"


class InstallType(StrEnum):
    WHOLE_CURRENT = "whole_current"
    CT_OPERATED = "ct_operated"
    UNKNOWN = "unknown"


class HierarchyLevel(StrEnum):
    ZONE = "zone"
    CIRCLE = "circle"
    DIVISION = "division"
    SUBDIVISION = "subdivision"
    SUBSTATION = "substation"
    FEEDER = "feeder"
    DT = "dt"


HIERARCHY_LEVELS: tuple[HierarchyLevel, ...] = tuple(HierarchyLevel)


@dataclass(frozen=True, slots=True)
class NodeRef:
    """One hierarchy node; a blank half is None, never an empty string."""

    code: str | None
    name: str | None


@dataclass(frozen=True, slots=True)
class HierarchyPath:
    """The seven-level network path of a meter."""

    zone: NodeRef
    circle: NodeRef
    division: NodeRef
    subdivision: NodeRef
    substation: NodeRef
    feeder: NodeRef
    dt: NodeRef

    def get(self, level: HierarchyLevel) -> NodeRef:
        """Return the node at the given level."""
        ref: NodeRef = getattr(self, level.value)
        return ref


@dataclass(frozen=True, slots=True)
class GeoPoint:
    lat: float
    lng: float

    def __post_init__(self) -> None:
        if not -90 <= self.lat <= 90:
            raise ValueError(f"latitude out of range: {self.lat}")
        if not -180 <= self.lng <= 180:
            raise ValueError(f"longitude out of range: {self.lng}")


@dataclass(frozen=True, slots=True)
class Meter:
    """A meter; None on an optional field means the source does not provide it."""

    meter_id: str
    serial_no: str
    make: str
    phase_type: PhaseType
    install_status: InstallStatus
    install_type: InstallType | None
    build: str | None
    dt_code: str | None
    hierarchy: HierarchyPath | None
    geo: GeoPoint | None


@dataclass(frozen=True, slots=True)
class Transformer:
    code: str
    name: str
    feeder_code: str | None
    capacity_kva: int


@dataclass(frozen=True, slots=True)
class Reading:
    """A cumulative register reading at a tz-aware instant."""

    at: datetime
    kwh_register: float
    kvah_register: float
    voltage_r: float | None

    def __post_init__(self) -> None:
        if self.at.tzinfo is None or self.at.utcoffset() is None:
            raise ValueError("Reading.at must be timezone-aware")
