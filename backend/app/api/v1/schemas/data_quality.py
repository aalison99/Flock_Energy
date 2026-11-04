"""Data-quality report schemas."""

from pydantic import BaseModel, Field

from app.core.pagination import Page
from app.services.quality.models import Issue, Severity
from app.services.results import CheckInfo


class CheckOut(BaseModel):
    """One registered check."""

    id: str = Field(description="Check id, usable as the `check` filter.")
    severity: Severity = Field(description="How serious an issue from this check is.")
    description: str = Field(description="What the check looks for.")


class IssueOut(BaseModel):
    """One finding."""

    check: str = Field(description="Id of the check that found it.")
    severity: Severity = Field(description="Severity of the check.")
    entity: str = Field(description="Kind of entity concerned: meter, transformer or node.")
    entity_id: str = Field(description="Meter id, DT code or hierarchy node id.")
    message: str = Field(description="Human-readable summary.")
    evidence: dict[str, object] = Field(description="Check-specific facts behind the finding.")


class DataQualityResponse(Page[IssueOut]):
    """A page of issues plus unfiltered counts per check."""

    summary: dict[str, int] = Field(
        description="Issue count per check id over all data, ignoring the filters."
    )
    checks: list[CheckOut] = Field(description="Every registered check.")


def to_check_out(check: CheckInfo) -> CheckOut:
    return CheckOut(id=check.id, severity=check.severity, description=check.description)


def to_issue_out(issue: Issue) -> IssueOut:
    return IssueOut(
        check=issue.check,
        severity=issue.severity,
        entity=issue.entity,
        entity_id=issue.entity_id,
        message=issue.message,
        evidence=dict(issue.evidence),
    )
