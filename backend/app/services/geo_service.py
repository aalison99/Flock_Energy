"""Geo search over the local index: meters near a point or inside a box."""

from dataclasses import dataclass

from app.domain.exceptions import IndexNotReadyError, ValidationError
from app.domain.models import GeoPoint, Meter
from app.repositories.interfaces import MeterRepository
from app.services.catalogs.indexed_catalog import to_meter_query
from app.services.geo import bounding_box, haversine_km
from app.services.interfaces import MeterFilters


@dataclass(frozen=True)
class BBoxResult:
    items: list[Meter]
    truncated: bool


class GeoService:
    def __init__(self, meters: MeterRepository) -> None:
        self._meters = meters

    async def near(
        self, center: GeoPoint, radius_km: float, limit: int, filters: MeterFilters
    ) -> list[tuple[Meter, float]]:
        """Meters within `radius_km` as (meter, distance_km), nearest first, at most `limit`."""
        total = await self._meters.count()
        if total == 0:
            raise IndexNotReadyError("the local index is empty; a sync is needed")
        min_lat, min_lng, max_lat, max_lng = bounding_box(center, radius_km)
        # The box is only a prefilter; its candidates are few, so none are cut before the
        # exact distance test (limit=total can never truncate).
        candidates = await self._meters.within_box(
            min_lat, min_lng, max_lat, max_lng, to_meter_query(filters), total
        )
        within = [
            (meter, distance)
            for meter in candidates
            if meter.geo is not None and (distance := haversine_km(center, meter.geo)) <= radius_km
        ]
        within.sort(key=lambda pair: (pair[1], pair[0].meter_id))
        return within[:limit]

    async def within_bbox(
        self,
        min_lat: float,
        min_lng: float,
        max_lat: float,
        max_lng: float,
        filters: MeterFilters,
        limit: int,
    ) -> BBoxResult:
        if min_lat > max_lat or min_lng > max_lng:
            raise ValidationError(
                "the box minimum must not exceed its maximum",
                details={
                    "min_lat": min_lat,
                    "max_lat": max_lat,
                    "min_lng": min_lng,
                    "max_lng": max_lng,
                },
            )
        if await self._meters.count() == 0:
            raise IndexNotReadyError("the local index is empty; a sync is needed")
        found = await self._meters.within_box(
            min_lat, min_lng, max_lat, max_lng, to_meter_query(filters), limit + 1
        )
        return BBoxResult(items=found[:limit], truncated=len(found) > limit)
