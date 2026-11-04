"""Query parameters shared by every endpoint that filters meters."""

from typing import Annotated

from fastapi import Query
from pydantic import StringConstraints

from app.domain.models import InstallStatus, InstallType, PhaseType
from app.services.interfaces import MeterFilters, MeterSort

MAX_REPEATED = 10
MAX_CODE_LENGTH = 32
_Code = Annotated[str, StringConstraints(max_length=MAX_CODE_LENGTH)]

_HIERARCHY_NOTE = (
    "Matches the code at that level wherever it occurs (e.g. division=D-01 matches every "
    "division coded D-01); path-exact filtering is not available yet."
)


def meter_filter_params(
    q: Annotated[
        str | None,
        Query(max_length=64, description="Case-insensitive text found in the meter id or serial."),
    ] = None,
    status: Annotated[
        list[InstallStatus] | None,
        Query(max_length=MAX_REPEATED, description="Installation status; repeat for any-of."),
    ] = None,
    make: Annotated[
        list[_Code] | None,
        Query(max_length=MAX_REPEATED, description="Exact manufacturer; repeat for any-of."),
    ] = None,
    phase: Annotated[PhaseType | None, Query(description="Electrical phase type.")] = None,
    install_type: Annotated[InstallType | None, Query(description="Installation type.")] = None,
    dt: Annotated[
        str | None,
        Query(pattern=r"^DT-\d{3}$", description="Distribution transformer code, e.g. DT-007."),
    ] = None,
    feeder: Annotated[
        str | None,
        Query(pattern=r"^F-\d{3}$", description=f"Feeder code, e.g. F-001. {_HIERARCHY_NOTE}"),
    ] = None,
    substation: Annotated[
        str | None,
        Query(max_length=MAX_CODE_LENGTH, description=f"Substation code. {_HIERARCHY_NOTE}"),
    ] = None,
    subdivision: Annotated[
        str | None,
        Query(max_length=MAX_CODE_LENGTH, description=f"Subdivision code. {_HIERARCHY_NOTE}"),
    ] = None,
    division: Annotated[
        str | None,
        Query(max_length=MAX_CODE_LENGTH, description=f"Division code. {_HIERARCHY_NOTE}"),
    ] = None,
    circle: Annotated[
        str | None, Query(max_length=MAX_CODE_LENGTH, description=f"Circle code. {_HIERARCHY_NOTE}")
    ] = None,
    zone: Annotated[
        str | None, Query(max_length=MAX_CODE_LENGTH, description=f"Zone code. {_HIERARCHY_NOTE}")
    ] = None,
    has_geo: Annotated[
        bool | None, Query(description="True: only meters with a position; false: only without.")
    ] = None,
    sort: Annotated[
        MeterSort,
        Query(
            description="Sort order; ties are broken by meter id. `status` sorts "
            "alphabetically on the stored value (decommissioned, faulty, installed, unknown), "
            "not by severity."
        ),
    ] = MeterSort.METER_ID,
) -> MeterFilters:
    """Collect the meter filter query parameters into one MeterFilters."""
    return MeterFilters(
        q=q,
        status=tuple(status or ()),
        make=tuple(make or ()),
        phase=phase,
        install_type=install_type,
        dt=dt,
        feeder=feeder,
        substation=substation,
        subdivision=subdivision,
        division=division,
        circle=circle,
        zone=zone,
        has_geo=has_geo,
        sort=sort,
    )
