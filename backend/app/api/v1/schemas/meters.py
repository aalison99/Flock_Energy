"""Meter response schemas and the pure mappings from domain/service types."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.models import (
    HIERARCHY_LEVELS,
    HierarchyLevel,
    InstallStatus,
    InstallType,
    Meter,
    PhaseType,
)
from app.services.interfaces import FacetField
from app.services.results import MeterDetailResult


class MeterSummary(BaseModel):
    """A meter as shown in lists."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "meter_id": "J100000",
                "serial_no": "SE33962",
                "make": "HPL",
                "phase_type": "single",
                "install_status": "decommissioned",
                "dt_code": "DT-001",
            }
        }
    )

    meter_id: str = Field(description="Portal meter id, J followed by six digits.")
    serial_no: str = Field(description="Manufacturer serial number.")
    make: str = Field(description="Meter manufacturer.")
    phase_type: PhaseType = Field(description="Electrical phase type.")
    install_status: InstallStatus = Field(description="Installation status.")
    dt_code: str | None = Field(description="Code of the distribution transformer, if known.")


class HierarchyNodeOut(BaseModel):
    """One level of the network hierarchy."""

    level: HierarchyLevel = Field(description="Hierarchy level.")
    code: str | None = Field(description="Node code; null when the portal left it blank.")
    name: str | None = Field(description="Node name; null when the portal left it blank.")


class GeoOut(BaseModel):
    """A geographic position."""

    lat: float = Field(description="Latitude in degrees.")
    lng: float = Field(description="Longitude in degrees.")


class MetaOut(BaseModel):
    """Provenance and freshness of the answer."""

    source: Literal["portal", "index"] = Field(
        description="Where the data came from: the live portal or the local index."
    )
    fetched_at: datetime = Field(
        description="When the data was fetched from the portal or last synced into the index (UTC)."
    )
    stale: bool = Field(
        description="True when the data is older than its freshness limit "
        "(portal cache TTL, or the index's maximum age)."
    )


class MeterDetail(BaseModel):
    """Full meter record with hierarchy, position and freshness metadata."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "meter_id": "J100000",
                "serial_no": "SE33962",
                "make": "HPL",
                "phase_type": "single",
                "install_status": "decommissioned",
                "install_type": "whole_current",
                "build": "legacy",
                "dt_code": "DT-001",
                "hierarchy": [
                    {"level": "zone", "code": "Z-01", "name": "Jaipur Zone 1"},
                    {"level": "circle", "code": "C-01", "name": "Circle 1"},
                    {"level": "division", "code": "D-01", "name": "Division 1"},
                    {"level": "subdivision", "code": "SD-01", "name": "Subdivision 1"},
                    {"level": "substation", "code": "SS-01", "name": "Substation 1"},
                    {"level": "feeder", "code": "F-001", "name": "Feeder 1"},
                    {"level": "dt", "code": "DT-001", "name": "Malviya Nagar DT 1"},
                ],
                "geo": {"lat": 26.938961002479868, "lng": 75.83095696146852},
                "meta": {
                    "source": "portal",
                    "fetched_at": "2026-11-04T12:00:00Z",
                    "stale": False,
                },
            }
        }
    )

    meter_id: str = Field(description="Portal meter id, J followed by six digits.")
    serial_no: str = Field(description="Manufacturer serial number.")
    make: str = Field(description="Meter manufacturer.")
    phase_type: PhaseType = Field(description="Electrical phase type.")
    install_status: InstallStatus = Field(description="Installation status.")
    install_type: InstallType | None = Field(description="Installation type, if known.")
    build: str | None = Field(description="Portal record format (legacy or v2), if known.")
    dt_code: str | None = Field(description="Code of the distribution transformer, if known.")
    hierarchy: list[HierarchyNodeOut] = Field(
        description="Network path from zone down to DT; empty when unavailable."
    )
    geo: GeoOut | None = Field(description="Position of the meter, if the portal has one.")
    meta: MetaOut = Field(description="Provenance and freshness of this answer.")


def to_meter_summary(meter: Meter) -> MeterSummary:
    return MeterSummary(
        meter_id=meter.meter_id,
        serial_no=meter.serial_no,
        make=meter.make,
        phase_type=meter.phase_type,
        install_status=meter.install_status,
        dt_code=meter.dt_code,
    )


def to_meter_detail(result: MeterDetailResult) -> MeterDetail:
    meter = result.meter
    hierarchy: list[HierarchyNodeOut] = []
    if meter.hierarchy is not None:
        for level in HIERARCHY_LEVELS:
            node = meter.hierarchy.get(level)
            hierarchy.append(HierarchyNodeOut(level=level, code=node.code, name=node.name))
    geo = GeoOut(lat=result.geo.lat, lng=result.geo.lng) if result.geo is not None else None
    return MeterDetail(
        meter_id=meter.meter_id,
        serial_no=meter.serial_no,
        make=meter.make,
        phase_type=meter.phase_type,
        install_status=meter.install_status,
        install_type=meter.install_type,
        build=meter.build,
        dt_code=meter.dt_code,
        hierarchy=hierarchy,
        geo=geo,
        meta=MetaOut(
            source=result.meta.source,
            fetched_at=result.meta.fetched_at,
            stale=result.meta.stale,
        ),
    )


class FacetsResponse(BaseModel):
    """Meter counts per attribute value, for building filter chips."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "facets": {
                    "status": {"installed": 238, "faulty": 90, "decommissioned": 75},
                    "phase": {"single": 277, "three": 126},
                }
            }
        }
    )

    facets: dict[str, dict[str, int]] = Field(
        description="For each requested field, the count of matching meters per value. Each "
        "field's counts apply every filter except that field's own; zero counts are omitted."
    )


def to_facets_response(facets: dict[FacetField, dict[str, int]]) -> FacetsResponse:
    return FacetsResponse(facets={field.value: counts for field, counts in facets.items()})
