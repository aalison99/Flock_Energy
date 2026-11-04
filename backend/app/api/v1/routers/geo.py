"""Geo search endpoints: meters near a point and meters inside a box (local index only)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.v1.params import meter_filter_params
from app.api.v1.schemas.common import error_responses
from app.api.v1.schemas.geo import (
    BBoxResponse,
    NearResponse,
    to_bbox_meter,
    to_near_meter,
)
from app.core.deps import get_geo_service
from app.domain.models import GeoPoint
from app.services.geo_service import GeoService
from app.services.interfaces import MeterFilters

router = APIRouter(tags=["geo"])


@router.get(
    "/geo/near",
    operation_id="findMetersNear",
    response_model=NearResponse,
    summary="Find meters near a point",
    description="Meters with a position within the radius, nearest first. Needs the local index.",
    responses=error_responses(409, 422),
)
async def find_meters_near(
    service: Annotated[GeoService, Depends(get_geo_service)],
    filters: Annotated[MeterFilters, Depends(meter_filter_params)],
    lat: Annotated[float, Query(ge=-90, le=90, description="Centre latitude in degrees.")],
    lng: Annotated[float, Query(ge=-180, le=180, description="Centre longitude in degrees.")],
    radius_km: Annotated[
        float, Query(gt=0, le=50, description="Search radius in kilometres (up to 50).")
    ] = 1.0,
    limit: Annotated[int, Query(ge=1, le=200, description="Maximum meters returned.")] = 50,
) -> NearResponse:
    found = await service.near(GeoPoint(lat, lng), radius_km, limit, filters)
    return NearResponse(items=[to_near_meter(meter, distance) for meter, distance in found])


@router.get(
    "/geo/bbox",
    operation_id="findMetersInBox",
    response_model=BBoxResponse,
    summary="Find meters in a bounding box",
    description=(
        "Meters with a position inside the inclusive box, by meter id. Needs the local index. "
        "A box crossing the antimeridian is not supported."
    ),
    responses=error_responses(409, 422),
)
async def find_meters_in_box(
    service: Annotated[GeoService, Depends(get_geo_service)],
    filters: Annotated[MeterFilters, Depends(meter_filter_params)],
    min_lat: Annotated[float, Query(ge=-90, le=90, description="South edge in degrees.")],
    min_lng: Annotated[float, Query(ge=-180, le=180, description="West edge in degrees.")],
    max_lat: Annotated[float, Query(ge=-90, le=90, description="North edge in degrees.")],
    max_lng: Annotated[float, Query(ge=-180, le=180, description="East edge in degrees.")],
    limit: Annotated[int, Query(ge=1, le=2000, description="Maximum meters returned.")] = 1000,
) -> BBoxResponse:
    result = await service.within_bbox(min_lat, min_lng, max_lat, max_lng, filters, limit)
    return BBoxResponse(
        items=[to_bbox_meter(meter) for meter in result.items], truncated=result.truncated
    )
