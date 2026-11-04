"""Pure geographic maths on a sphere (no I/O)."""

import math

from app.domain.models import GeoPoint

EARTH_RADIUS_KM = 6371.0088
_KM_PER_DEG_LAT = EARTH_RADIUS_KM * math.pi / 180


def haversine_km(a: GeoPoint, b: GeoPoint) -> float:
    """Great-circle distance in kilometres."""
    lat1, lat2 = math.radians(a.lat), math.radians(b.lat)
    d_lat = lat2 - lat1
    d_lng = math.radians(b.lng - a.lng)
    h = math.sin(d_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(d_lng / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(h)))


def bounding_box(center: GeoPoint, radius_km: float) -> tuple[float, float, float, float]:
    """(min_lat, min_lng, max_lat, max_lng) that contains every point within `radius_km`.

    The longitude span is widened by 1/cos(lat) at the box's highest-latitude edge, so the
    box is safe (slightly generous) rather than tight. Latitudes are clamped to +-90; when
    the circle reaches a pole every longitude is included. The antimeridian is not handled:
    a box crossing +-180 degrees is clamped, so points just across it are missed.
    """
    padded_km = radius_km * (1 + 1e-9) + 1e-9  # absorbs float rounding at the exact edge
    d_lat = padded_km / _KM_PER_DEG_LAT
    min_lat = max(center.lat - d_lat, -90.0)
    max_lat = min(center.lat + d_lat, 90.0)
    widest_lat = max(abs(min_lat), abs(max_lat))
    if widest_lat >= 90.0:
        return min_lat, -180.0, max_lat, 180.0
    d_lng = math.degrees(
        math.asin(min(1.0, math.sin(d_lat * math.pi / 180) / math.cos(math.radians(widest_lat))))
    )
    return min_lat, max(center.lng - d_lng, -180.0), max_lat, min(center.lng + d_lng, 180.0)
