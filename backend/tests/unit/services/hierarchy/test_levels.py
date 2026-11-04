import pytest

from app.domain.models import HIERARCHY_LEVELS, HierarchyLevel
from app.services.hierarchy.levels import LEVEL_RULES, code_from_name, name_from_code


@pytest.mark.parametrize(
    ("level", "name", "code"),
    [
        (HierarchyLevel.ZONE, "Jaipur Zone 1", "Z-01"),
        (HierarchyLevel.CIRCLE, "Circle 6", "C-06"),
        (HierarchyLevel.DIVISION, "Division 12", "D-12"),
        (HierarchyLevel.SUBDIVISION, "Subdivision 7", "SD-07"),
        (HierarchyLevel.SUBSTATION, "Substation 40", "SS-40"),
        (HierarchyLevel.FEEDER, "Feeder 5", "F-005"),
        (HierarchyLevel.FEEDER, "Feeder 123", "F-123"),
    ],
)
def test_both_directions_with_padding(level: HierarchyLevel, name: str, code: str) -> None:
    assert code_from_name(level, name) == code
    assert name_from_code(level, code) == name


@pytest.mark.parametrize(
    ("level", "text"),
    [
        (HierarchyLevel.CIRCLE, "Division 6"),
        (HierarchyLevel.CIRCLE, "Circle"),
        (HierarchyLevel.CIRCLE, "Circle six"),
        (HierarchyLevel.CIRCLE, " Circle 6"),
        (HierarchyLevel.ZONE, "Zone 1"),
        (HierarchyLevel.DT, "Sanganer DT 7"),
        (HierarchyLevel.DT, ""),
    ],
)
def test_names_that_do_not_fit_give_none(level: HierarchyLevel, text: str) -> None:
    assert code_from_name(level, text) is None


@pytest.mark.parametrize(
    ("level", "text"),
    [
        (HierarchyLevel.CIRCLE, "C-6"),
        (HierarchyLevel.CIRCLE, "D-06"),
        (HierarchyLevel.CIRCLE, "C06"),
        (HierarchyLevel.FEEDER, "F-05"),
        (HierarchyLevel.SUBDIVISION, "S-07"),
        (HierarchyLevel.DT, "DT-007"),
        (HierarchyLevel.CIRCLE, ""),
    ],
)
def test_codes_that_do_not_fit_give_none(level: HierarchyLevel, text: str) -> None:
    assert name_from_code(level, text) is None


def test_every_level_has_a_rule() -> None:
    assert set(LEVEL_RULES) == set(HIERARCHY_LEVELS)
