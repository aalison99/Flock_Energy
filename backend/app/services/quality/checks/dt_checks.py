"""Checks that compare meters, the DT list and the tree's DT placement."""

from app.domain.models import HierarchyLevel
from app.services.quality.models import Issue, QualityContext, Severity


class DtCodeMismatch:
    id = "dt_code_mismatch"
    severity = Severity.WARNING
    description = (
        "A meter's own dt_code differs from the DT code in its (repaired) hierarchy path; "
        "unplaced meters are skipped."
    )

    def run(self, ctx: QualityContext) -> list[Issue]:
        placed_dt = {
            meter_id: node.code
            for node in ctx.snapshot.nodes.values()
            if node.level is HierarchyLevel.DT
            for meter_id in node.meter_ids
        }
        issues: list[Issue] = []
        for m in ctx.meters:
            if m.meter_id not in placed_dt or m.dt_code == placed_dt[m.meter_id]:
                continue
            issues.append(
                Issue(
                    self.id,
                    self.severity,
                    "meter",
                    m.meter_id,
                    f"dt_code {m.dt_code} differs from hierarchy DT {placed_dt[m.meter_id]}",
                    {"dt_code": m.dt_code, "hierarchy_dt_code": placed_dt[m.meter_id]},
                )
            )
        return issues


class UnknownDt:
    id = "unknown_dt"
    severity = Severity.WARNING
    description = "A meter names a DT code that is not in the portal's DT list."

    def run(self, ctx: QualityContext) -> list[Issue]:
        known = {t.code for t in ctx.transformers}
        return [
            Issue(
                self.id,
                self.severity,
                "meter",
                m.meter_id,
                f"DT {m.dt_code} is not in the DT list",
                {"dt_code": m.dt_code},
            )
            for m in ctx.meters
            if m.dt_code is not None and m.dt_code not in known
        ]


class DtWithoutMeters:
    id = "dt_without_meters"
    severity = Severity.INFO
    description = "A DT in the DT list has no meters."

    def run(self, ctx: QualityContext) -> list[Issue]:
        used = {m.dt_code for m in ctx.meters}
        used.update(n.code for n in ctx.snapshot.nodes.values() if n.level is HierarchyLevel.DT)
        return [
            Issue(
                self.id,
                self.severity,
                "transformer",
                t.code,
                f"DT {t.code} has no meters",
                {"name": t.name},
            )
            for t in ctx.transformers
            if t.code not in used
        ]


class DtFeederMismatch:
    id = "dt_feeder_mismatch"
    severity = Severity.WARNING
    description = (
        "The DT list's feeder differs from the feeder its meters' paths show. Feeder codes "
        "repeat across substations, so only the bare code is compared."
    )

    def run(self, ctx: QualityContext) -> list[Issue]:
        nodes = ctx.snapshot.nodes
        path_feeders: dict[str, set[str]] = {}
        for node in nodes.values():
            if node.level is HierarchyLevel.DT and node.parent_id is not None:
                path_feeders.setdefault(node.code, set()).add(nodes[node.parent_id].code)
        issues: list[Issue] = []
        for t in ctx.transformers:
            seen = path_feeders.get(t.code)
            if t.feeder_code is None or not seen or seen == {t.feeder_code}:
                continue
            issues.append(
                Issue(
                    self.id,
                    self.severity,
                    "transformer",
                    t.code,
                    f"DT list says feeder {t.feeder_code}; meters sit under {sorted(seen)}",
                    {"list_feeder_code": t.feeder_code, "path_feeder_codes": sorted(seen)},
                )
            )
        return issues
