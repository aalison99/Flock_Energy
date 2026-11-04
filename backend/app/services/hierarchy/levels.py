"""The number rule: one table tying each level's code ("C-06") to its name ("Circle 6")."""

import re
from dataclasses import dataclass

from app.domain.models import HierarchyLevel


@dataclass(frozen=True)
class LevelRule:
    """`prefix` and `digits` shape the code; `name_prefix` shapes the name (None: free text)."""

    prefix: str
    digits: int
    name_prefix: str | None

    @property
    def code_re(self) -> re.Pattern[str]:
        return re.compile(rf"{re.escape(self.prefix)}-(\d{{{self.digits},}})")

    @property
    def name_re(self) -> re.Pattern[str] | None:
        if self.name_prefix is None:
            return None
        return re.compile(rf"{re.escape(self.name_prefix)} (\d+)")


LEVEL_RULES: dict[HierarchyLevel, LevelRule] = {
    HierarchyLevel.ZONE: LevelRule("Z", 2, "Jaipur Zone"),
    HierarchyLevel.CIRCLE: LevelRule("C", 2, "Circle"),
    HierarchyLevel.DIVISION: LevelRule("D", 2, "Division"),
    HierarchyLevel.SUBDIVISION: LevelRule("SD", 2, "Subdivision"),
    HierarchyLevel.SUBSTATION: LevelRule("SS", 2, "Substation"),
    HierarchyLevel.FEEDER: LevelRule("F", 3, "Feeder"),
    HierarchyLevel.DT: LevelRule("DT", 3, None),  # DT names come from the DT list
}


def code_from_name(level: HierarchyLevel, name: str) -> str | None:
    """ "Circle 6" -> "C-06"; None when the name does not fit the level's pattern."""
    rule = LEVEL_RULES[level]
    pattern = rule.name_re
    match = pattern.fullmatch(name) if pattern is not None else None
    if match is None:
        return None
    return f"{rule.prefix}-{int(match.group(1)):0{rule.digits}d}"


def name_from_code(level: HierarchyLevel, code: str) -> str | None:
    """ "C-06" -> "Circle 6"; None when the code does not fit or the level has no name rule."""
    rule = LEVEL_RULES[level]
    match = rule.code_re.fullmatch(code)
    if match is None or rule.name_prefix is None:
        return None
    return f"{rule.name_prefix} {int(match.group(1))}"
