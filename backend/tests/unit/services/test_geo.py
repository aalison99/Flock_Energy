import math

import pytest

from app.domain.models import GeoPoint
from app.services.geo import bounding_box, haversine_km

JAIPUR = GeoPoint(26.9124, 75.7873)
AIRPORT = GeoPoint(26.8242, 75.8122)  # Jaipur International, ~10 km south
DELHI = GeoPoint(28.6139, 77.2090)


def test_zero_distance() -> None:
    assert haversine_km(JAIPUR, JAIPUR) == 0.0


def test_symmetric() -> None:
    assert haversine_km(JAIPUR, DELHI) == pytest.approx(haversine_km(DELHI, JAIPUR), abs=1e-12)


def test_one_degree_of_latitude() -> None:
    expected = 6371.0088 * math.pi / 180  # R * 1 degree in radians
    assert haversine_km(GeoPoint(10, 20), GeoPoint(11, 20)) == pytest.approx(expected, abs=1e-6)
    assert expected == pytest.approx(111.195, abs=1e-3)


def test_one_degree_of_longitude_at_the_equator() -> None:
    expected = 6371.0088 * math.pi / 180
    assert haversine_km(GeoPoint(0, 10), GeoPoint(0, 11)) == pytest.approx(expected, abs=1e-6)


@pytest.mark.parametrize(
    ("a", "b", "reference_km"),
    [
        (JAIPUR, DELHI, 235.2906),  # standalone haversine script, R = 6371.0088
        (JAIPUR, AIRPORT, 10.1136),
        (GeoPoint(0, 0), GeoPoint(0, 180), math.pi * 6371.0088),
    ],
)
def test_reference_pairs_within_one_metre(a: GeoPoint, b: GeoPoint, reference_km: float) -> None:
    assert haversine_km(a, b) == pytest.approx(reference_km, abs=0.001)


def _point_at(center: GeoPoint, bearing_deg: float, km: float) -> GeoPoint:
    """Destination on a sphere (same radius as haversine_km)."""
    d = km / 6371.0088
    b, lat1, lng1 = map(math.radians, (bearing_deg, center.lat, center.lng))
    lat2 = math.asin(math.sin(lat1) * math.cos(d) + math.cos(lat1) * math.sin(d) * math.cos(b))
    lng2 = lng1 + math.atan2(
        math.sin(b) * math.sin(d) * math.cos(lat1), math.cos(d) - math.sin(lat1) * math.sin(lat2)
    )
    return GeoPoint(math.degrees(lat2), math.degrees(lng2))


@pytest.mark.parametrize("center", [JAIPUR, GeoPoint(0, 0), GeoPoint(60, 10), GeoPoint(-45, -100)])
@pytest.mark.parametrize("radius", [0.1, 1.0, 5.0, 50.0])
@pytest.mark.parametrize("bearing", [0, 45, 90, 135, 180, 225, 270, 315])
def test_box_contains_points_at_exactly_the_radius(
    center: GeoPoint, radius: float, bearing: float
) -> None:
    min_lat, min_lng, max_lat, max_lng = bounding_box(center, radius)
    point = _point_at(center, bearing, radius)
    assert min_lat <= point.lat <= max_lat
    assert min_lng <= point.lng <= max_lng


def test_box_is_centered_and_clamped_at_the_poles() -> None:
    min_lat, min_lng, max_lat, max_lng = bounding_box(GeoPoint(89.99, 10), 50)
    assert max_lat == 90.0
    assert (min_lng, max_lng) == (-180.0, 180.0)  # at the pole every longitude is in reach
    assert min_lat < 89.99


def test_box_matches_axis_distances() -> None:
    min_lat, _, max_lat, max_lng = bounding_box(JAIPUR, 5.0)
    assert haversine_km(JAIPUR, GeoPoint(max_lat, JAIPUR.lng)) == pytest.approx(5.0, abs=0.01)
    assert haversine_km(JAIPUR, GeoPoint(JAIPUR.lat, max_lng)) >= 5.0
    assert (min_lat + max_lat) / 2 == pytest.approx(JAIPUR.lat)
