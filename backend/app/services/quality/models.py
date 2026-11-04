"""Data-quality vocabulary: severities, issues, the context checks read and the check Protocol."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Protocol

from app.domain.models import Meter, Transformer
from app.services.hierarchy.builder import HierarchySnapshot


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


SEVERITY_ORDER: tuple[Severity, ...] = (Severity.ERROR, Severity.WARNING, Severity.INFO)

Entity = Literal["meter", "transformer", "node"]


@dataclass(frozen=True)
class Issue:
    check: str
    severity: Severity
    entity: Entity
    entity_id: str
    message: str
    evidence: Mapping[str, object]


@dataclass(frozen=True)
class QualityContext:
    """Everything a check may look at: the raw inputs and the tree built from them."""

    meters: Sequence[Meter]
    transformers: Sequence[Transformer]
    snapshot: HierarchySnapshot


class QualityCheck(Protocol):
    id: str
    severity: Severity
    description: str

    def run(self, ctx: QualityContext) -> list[Issue]: ...
