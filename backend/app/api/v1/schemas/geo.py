"""Geo search response schemas."""

from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.schemas.meters import MeterSummary, to_meter_summary
from app.domain.models import InstallStatus, Meter


class NearMeter(BaseModel):
    """A meter found near a point, with its position and distance."""

    meter: MeterSummary = Field(description="The meter.")
    lat: float = Field(description="Latitude in degrees.")
    lng: float = Field(description="Longitude in degrees.")
    distance_km: float = Field(description="Great-circle distance from the search point in km.")


class NearResponse(BaseModel):
    """Meters within a radius, nearest first."""

    items: list[NearMeter] = Field(description="Meters ordered by distance, then meter id.")


class BBoxMeter(BaseModel):
    """A meter inside a bounding box (the slim shape a map needs)."""

    meter_id: str = Field(description="Portal meter id, J followed by six digits.")
    lat: float = Field(description="Latitude in degrees.")
    lng: float = Field(description="Longitude in degrees.")
    install_status: InstallStatus = Field(description="Installation status.")
    dt_code: str | None = Field(description="Code of the distribution transformer, if known.")


class BBoxResponse(BaseModel):
    """Meters inside a bounding box."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "items": [
                    {
                        "meter_id": "J100000",
                        "lat": 26.938961002479868,
                        "lng": 75.83095696146852,
                        "install_status": "decommissioned",
                        "dt_code": "DT-001",
                    }
                ],
                "truncated": False,
            }
        }
    )

    items: list[BBoxMeter] = Field(description="Meters by meter id, at most `limit`.")
    truncated: bool = Field(description="True when more meters matched than `limit` allowed.")


def to_near_meter(meter: Meter, distance_km: float) -> NearMeter:
    assert meter.geo is not None  # the geo query only returns meters with a position
    return NearMeter(
        meter=to_meter_summary(meter),
        lat=meter.geo.lat,
        lng=meter.geo.lng,
        distance_km=round(distance_km, 3),
    )


def to_bbox_meter(meter: Meter) -> BBoxMeter:
    assert meter.geo is not None
    return BBoxMeter(
        meter_id=meter.meter_id,
        lat=meter.geo.lat,
        lng=meter.geo.lng,
        install_status=meter.install_status,
        dt_code=meter.dt_code,
    )
