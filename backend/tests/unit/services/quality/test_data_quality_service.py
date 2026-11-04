import pytest

from app.domain.exceptions import IndexNotReadyError, ValidationError
from app.services.data_quality_service import DataQualityService
from app.services.quality.models import Issue, QualityContext, Severity
from app.services.quality.registry import CHECKS
from tests.support.fakes import FakeMeterRepository, FakeTransformerRepository
from tests.support.hierarchy_factory import make_meter, make_transformer

pytestmark = pytest.mark.anyio


class StubCheck:
    def __init__(self, id: str, severity: Severity, entity_ids: list[str]) -> None:
        self.id = id
        self.severity = severity
        self.description = f"stub {id}"
        self._ids = entity_ids

    def run(self, ctx: QualityContext) -> list[Issue]:
        return [Issue(self.id, self.severity, "meter", i, "m", {}) for i in self._ids]


def service(*checks: StubCheck) -> DataQualityService:
    repo = FakeMeterRepository([make_meter("J1")])
    return DataQualityService(checks, repo, FakeTransformerRepository([make_transformer()]))


STUBS = (
    StubCheck("b_info", Severity.INFO, ["J3", "J1"]),
    StubCheck("a_warn", Severity.WARNING, ["J2"]),
    StubCheck("z_err", Severity.ERROR, ["J9"]),
    StubCheck("m_warn", Severity.WARNING, ["J5", "J4"]),
)


async def test_items_ordered_by_severity_then_check_then_entity() -> None:
    report = await service(*STUBS).report(None, None, 1, 50)
    assert [(i.check, i.entity_id) for i in report.items.items] == [
        ("z_err", "J9"),
        ("a_warn", "J2"),
        ("m_warn", "J4"),
        ("m_warn", "J5"),
        ("b_info", "J1"),
        ("b_info", "J3"),
    ]
    assert report.items.total == 6


async def test_summary_and_check_list_ignore_filters() -> None:
    report = await service(*STUBS).report("m_warn", Severity.WARNING, 1, 50)
    assert report.summary == {"b_info": 2, "a_warn": 1, "z_err": 1, "m_warn": 2}
    first = report.checks[0]
    assert (first.id, first.severity, first.description) == (
        "b_info",
        Severity.INFO,
        "stub b_info",
    )
    assert report.items.total == 2


async def test_filters_combine() -> None:
    by_check = await service(*STUBS).report("b_info", None, 1, 50)
    assert {i.check for i in by_check.items.items} == {"b_info"}
    by_severity = await service(*STUBS).report(None, Severity.WARNING, 1, 50)
    assert by_severity.items.total == 3
    none = await service(*STUBS).report("b_info", Severity.ERROR, 1, 50)
    assert none.items.total == 0


async def test_pagination_slices_after_ordering() -> None:
    page2 = await service(*STUBS).report(None, None, 2, 4)
    assert [i.entity_id for i in page2.items.items] == ["J1", "J3"]
    assert page2.items.total == 6


async def test_unknown_check_is_a_validation_error_listing_valid_ids() -> None:
    with pytest.raises(ValidationError) as err:
        await service(*STUBS).report("nope", None, 1, 10)
    assert err.value.details["valid"] == ["b_info", "a_warn", "z_err", "m_warn"]


async def test_empty_index_is_not_ready() -> None:
    empty = DataQualityService(STUBS, FakeMeterRepository([]), FakeTransformerRepository([]))
    with pytest.raises(IndexNotReadyError):
        await empty.report(None, None, 1, 10)


async def test_real_registry_runs_end_to_end_on_a_clean_meter() -> None:
    report = await DataQualityService(
        CHECKS,
        FakeMeterRepository([make_meter("J1")]),
        FakeTransformerRepository([make_transformer()]),
    ).report(None, None, 1, 10)
    assert set(report.summary) == {c.id for c in CHECKS}
    assert report.items.total == 0
