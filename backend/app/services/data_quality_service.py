"""The data-quality report: runs every registered check over the indexed data."""

from collections.abc import Sequence

from app.domain.exceptions import IndexNotReadyError, ValidationError
from app.domain.models import PageResult
from app.repositories.interfaces import MeterRepository, TransformerRepository
from app.services.hierarchy.builder import build_hierarchy
from app.services.quality.models import (
    SEVERITY_ORDER,
    QualityCheck,
    QualityContext,
    Severity,
)
from app.services.results import CheckInfo, QualityReport

_RANK = {severity: rank for rank, severity in enumerate(SEVERITY_ORDER)}


class DataQualityService:
    def __init__(
        self,
        checks: Sequence[QualityCheck],
        meters: MeterRepository,
        transformers: TransformerRepository,
    ) -> None:
        self._checks = checks
        self._meters = meters
        self._transformers = transformers

    async def report(
        self, check: str | None, severity: Severity | None, page: int, page_size: int
    ) -> QualityReport:
        """Counts per check over everything; items filtered, ordered, then paged."""
        valid = [c.id for c in self._checks]
        if check is not None and check not in valid:
            raise ValidationError(f"unknown check {check}", details={"valid": valid})
        meters = await self._meters.list_all()
        if not meters:
            raise IndexNotReadyError("the local index is empty; a sync is needed")
        transformers = await self._transformers.list_all()
        ctx = QualityContext(meters, transformers, build_hierarchy(meters, transformers))

        found = {c.id: c.run(ctx) for c in self._checks}
        issues = [
            i
            for i in (i for batch in found.values() for i in batch)
            if (check is None or i.check == check) and (severity is None or i.severity == severity)
        ]
        issues.sort(key=lambda i: (_RANK[i.severity], i.check, i.entity_id))
        start = (page - 1) * page_size
        return QualityReport(
            summary={c.id: len(found[c.id]) for c in self._checks},
            checks=[CheckInfo(c.id, c.severity, c.description) for c in self._checks],
            items=PageResult(items=issues[start : start + page_size], total=len(issues)),
        )
