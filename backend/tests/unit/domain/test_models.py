"""Domain model invariants: geo ranges, tz-aware readings, hierarchy lookup."""

from datetime import UTC, datetime

import pytest

from app.domain.models import (
    HIERARCHY_LEVELS,
    GeoPoint,
    HierarchyLevel,
    HierarchyPath,
    NodeRef,
    Reading,
)


@pytest.mark.parametrize("lat,lng", [(90.1, 0), (-90.1, 0), (0, 180.1), (0, -180.1)])
def test_geo_out_of_range(lat: float, lng: float) -> None:
    with pytest.raises(ValueError):
        GeoPoint(lat, lng)


def test_geo_in_range() -> None:
    assert GeoPoint(26.9, 75.8).lat == 26.9
    GeoPoint(90, 180)
    GeoPoint(-90, -180)


def test_reading_requires_tz() -> None:
    with pytest.raises(ValueError):
        Reading(datetime(2026, 1, 1), 1.0, 2.0, None)
    assert Reading(datetime(2026, 1, 1, tzinfo=UTC), 1.0, 2.0, None).voltage_r is None


def test_hierarchy_get_every_level() -> None:
    refs = {lvl: NodeRef(f"c-{lvl}", f"n-{lvl}") for lvl in HIERARCHY_LEVELS}
    path = HierarchyPath(**{lvl.value: ref for lvl, ref in refs.items()})
    assert len(HIERARCHY_LEVELS) == 7
    assert HIERARCHY_LEVELS[0] is HierarchyLevel.ZONE
    assert HIERARCHY_LEVELS[-1] is HierarchyLevel.DT
    for lvl in HIERARCHY_LEVELS:
        assert path.get(lvl) == refs[lvl]


def test_sync_enums_have_stable_values() -> None:
    from app.domain.models import SyncStatus, SyncStrategy

    assert [s.value for s in SyncStatus] == ["running", "succeeded", "failed"]
    assert [s.value for s in SyncStrategy] == ["export", "crawl"]


def test_sync_run_is_frozen() -> None:
    from dataclasses import FrozenInstanceError
    from datetime import UTC, datetime

    import pytest

    from app.domain.models import SyncRun, SyncStatus

    run = SyncRun(1, SyncStatus.RUNNING, None, datetime(2026, 1, 1, tzinfo=UTC), None, {}, None)
    with pytest.raises(FrozenInstanceError):
        run.id = 2  # type: ignore[misc]
