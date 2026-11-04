"""Checks about how the tree was built: aliases, repairs, unplaced meters, DT parent conflicts."""

from app.domain.models import HierarchyLevel
from app.services.quality.models import Issue, QualityContext, Severity


class NameConflict:
    id = "name_conflict"
    severity = Severity.WARNING
    description = "A hierarchy node is called by more than one name (the canonical name wins)."

    def run(self, ctx: QualityContext) -> list[Issue]:
        listed = {t.code for t in ctx.transformers}
        issues: list[Issue] = []
        for node in ctx.snapshot.nodes.values():
            if not node.alt_names:
                continue
            from_list = node.level is HierarchyLevel.DT and node.code in listed
            issues.append(
                Issue(
                    self.id,
                    self.severity,
                    "node",
                    node.id,
                    f"{node.id} is named '{node.name}' but also "
                    + ", ".join(f"'{a.name}'" for a in node.alt_names),
                    {
                        "canonical": node.name,
                        "canonical_source": "dt_list" if from_list else "most_common_name",
                        "aliases": [
                            {"name": a.name, "meter_ids": list(a.meter_ids)} for a in node.alt_names
                        ],
                    },
                )
            )
        return sorted(issues, key=lambda i: i.entity_id)


class BlankFieldRepaired:
    id = "blank_field_repaired"
    severity = Severity.INFO
    description = "A blank hierarchy code or name was filled in; before and after are shown."

    def run(self, ctx: QualityContext) -> list[Issue]:
        return [
            Issue(
                self.id,
                self.severity,
                "meter",
                r.meter_id,
                f"blank {r.level.value} {r.field} repaired as '{r.after}' ({r.method})",
                {
                    "level": r.level.value,
                    "field": r.field,
                    "before": r.before,
                    "after": r.after,
                    "method": r.method,
                },
            )
            for r in ctx.snapshot.repairs
        ]


class UnplacedMeter:
    id = "unplaced_meter"
    severity = Severity.WARNING
    description = "A meter could not be placed all the way down the tree (blank, unrepairable)."

    def run(self, ctx: QualityContext) -> list[Issue]:
        parent_of = {
            meter_id: node.id for node in ctx.snapshot.nodes.values() for meter_id in node.meter_ids
        }
        return [
            Issue(
                self.id,
                self.severity,
                "meter",
                meter_id,
                f"meter {meter_id} could not be placed fully in the hierarchy",
                {"placed_under": parent_of.get(meter_id)},
            )
            for meter_id in ctx.snapshot.unplaced
        ]


class ParentConflictCheck:
    id = "parent_conflict"
    severity = Severity.ERROR
    description = "One DT code appears under more than one parent path (DT codes are unique)."

    def run(self, ctx: QualityContext) -> list[Issue]:
        return [
            Issue(
                self.id,
                self.severity,
                "transformer",
                c.code,
                f"{c.code} appears under {len(c.paths)} different parents",
                {"paths": list(c.paths), "meter_ids": list(c.meter_ids)},
            )
            for c in ctx.snapshot.conflicts
        ]
