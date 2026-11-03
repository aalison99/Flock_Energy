"""Detail pages and the export must agree; the whole export must map cleanly."""

import dataclasses
from collections import Counter
from pathlib import Path

import pytest

from app.domain.models import (
    HIERARCHY_LEVELS,
    InstallStatus,
    InstallType,
    Meter,
    PhaseType,
)
from app.portal.interfaces import PortalPage
from app.portal.parsers.registry import PayloadKind, default_registry

FIX = Path(__file__).parents[2] / "fixtures" / "portal"
registry = default_registry()


@pytest.fixture(scope="module")
def export() -> dict[str, Meter]:
    out = registry.parse(PayloadKind.EXPORT, (FIX / "export" / "export_page1.json").read_bytes())
    assert isinstance(out, list)
    return {m.meter_id: m for m in out}


@pytest.mark.parametrize(
    "meter_id,fixture",
    [
        ("J100000", "detail_legacy_J100000"),
        ("J100086", "detail_v2_J100086"),
        ("J100402", "detail_legacy_J100402_old_dt_name"),
    ],
)
def test_detail_equals_export(export: dict[str, Meter], meter_id: str, fixture: str) -> None:
    detail = registry.parse(
        PayloadKind.METER_DETAIL, (FIX / "meters" / f"{fixture}.json").read_bytes()
    )
    assert dataclasses.replace(export[meter_id], geo=None) == detail


def test_whole_export_counts(export: dict[str, Meter]) -> None:
    ms = list(export.values())
    assert len(ms) == 403
    assert Counter(m.install_status for m in ms) == {
        InstallStatus.INSTALLED: 238,
        InstallStatus.FAULTY: 90,
        InstallStatus.DECOMMISSIONED: 75,
    }
    assert Counter(m.phase_type for m in ms) == {PhaseType.SINGLE: 277, PhaseType.THREE: 126}
    assert Counter(m.install_type for m in ms) == {
        InstallType.WHOLE_CURRENT: 205,
        InstallType.CT_OPERATED: 198,
    }
    assert Counter(m.build for m in ms) == {"legacy": 238, "v2": 165}


def test_blank_node_halves(export: dict[str, Meter]) -> None:
    blanks = [
        m
        for m in export.values()
        if m.hierarchy
        and any(
            m.hierarchy.get(lvl).code is None or m.hierarchy.get(lvl).name is None
            for lvl in HIERARCHY_LEVELS
        )
    ]
    assert len(blanks) == 22


def test_search_agrees_with_export(export: dict[str, Meter]) -> None:
    page = registry.parse(
        PayloadKind.SEARCH_PAGE, (FIX / "meters" / "search_page1.json").read_bytes()
    )
    assert isinstance(page, PortalPage)
    for m in page.items:
        full = export[m.meter_id]
        assert (
            dataclasses.replace(full, install_type=None, build=None, hierarchy=None, geo=None) == m
        )
