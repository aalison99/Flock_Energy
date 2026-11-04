import pytest

from app.domain.models import GeoPoint
from app.services.quality.checks.geo_checks import GeoOutlier
from app.services.quality.models import Severity
from tests.support.hierarchy_factory import make_meter, quality_context


def _cluster() -> list:
    return [make_meter(f"J{i}", geo=GeoPoint(26.9 + i * 0.001, 75.8)) for i in range(5)]


def test_flags_a_meter_over_50_km_from_the_median() -> None:
    far = make_meter("J9", geo=GeoPoint(27.9, 75.8))  # about 111 km north
    (issue,) = GeoOutlier().run(quality_context([*_cluster(), far]))
    assert (issue.check, issue.severity, issue.entity, issue.entity_id) == (
        "geo_outlier",
        Severity.WARNING,
        "meter",
        "J9",
    )
    assert issue.evidence["median_lat"] == pytest.approx(26.9025)
    assert issue.evidence["median_lng"] == 75.8
    assert 105 < issue.evidence["distance_km"] < 115  # type: ignore[operator]


def test_a_meter_just_inside_50_km_is_fine() -> None:
    near = make_meter("J9", geo=GeoPoint(27.3, 75.8))  # about 44 km
    assert GeoOutlier().run(quality_context([*_cluster(), near])) == []


def test_no_positions_no_outliers() -> None:
    assert GeoOutlier().run(quality_context([make_meter("J1", geo=None)])) == []
