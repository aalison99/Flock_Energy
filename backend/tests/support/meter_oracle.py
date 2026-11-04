"""Brute-force reference for meter search: plain Python over a list, no SQL.

Works with any filters object that has the MeterFilters / MeterQuery field names, so the
repository, catalog and integration tests all share one oracle.
"""

from collections import Counter
from dataclasses import fields, replace
from typing import Any

from app.domain.models import HierarchyLevel, Meter

_LEVEL_FIELDS = ("zone", "circle", "division", "subdivision", "substation", "feeder")
_SORT_KEYS: dict[str, Any] = {
    "meter_id": lambda m: (m.meter_id,),
    "make": lambda m: (m.make, m.meter_id),
    "status": lambda m: (m.install_status.value, m.meter_id),
}
FACET_VALUE: dict[str, Any] = {
    "status": lambda m: m.install_status.value,
    "make": lambda m: m.make,
    "phase": lambda m: m.phase_type.value,
    "install_type": lambda m: m.install_type.value if m.install_type else None,
    "dt": lambda m: m.dt_code,
}


def matches(meter: Meter, f: Any) -> bool:
    if f.q is not None:
        needle = f.q.lower()
        if needle not in meter.meter_id.lower() and needle not in meter.serial_no.lower():
            return False
    if f.status and meter.install_status.value not in f.status:
        return False
    if f.make and meter.make not in f.make:
        return False
    if f.phase is not None and meter.phase_type.value != f.phase:
        return False
    if f.install_type is not None and (
        meter.install_type is None or meter.install_type.value != f.install_type
    ):
        return False
    if f.dt is not None and meter.dt_code != f.dt:
        return False
    for level in _LEVEL_FIELDS:
        wanted = getattr(f, level)
        if wanted is None:
            continue
        if meter.hierarchy is None:
            return False
        if meter.hierarchy.get(HierarchyLevel(level)).code != wanted:
            return False
    return not (f.has_geo is not None and (meter.geo is not None) != f.has_geo)


def search(meters: list[Meter], f: Any) -> list[Meter]:
    """Matching meters in the filter's sort order (`-meter_id` reverses)."""
    sort = str(f.sort)
    descending = sort.startswith("-")
    key = _SORT_KEYS[sort.lstrip("-")]
    found = [m for m in meters if matches(m, f)]
    return sorted(found, key=key, reverse=descending)


def facet(meters: list[Meter], f: Any, field: str) -> dict[str, int]:
    """Counts of `field` with every filter applied except the field's own."""
    default = next(fld.default for fld in fields(f) if fld.name == field)
    other = replace(f, **{field: default})
    values = (FACET_VALUE[field](m) for m in meters if matches(m, other))
    return dict(Counter(v for v in values if v is not None))
