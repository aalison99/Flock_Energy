"""The registered quality checks: add a class to this tuple to add a check.

`serial_make_mismatch` is deliberately absent: serial prefixes do not correspond to the make
(PROTOCOL section 4.2), so such a check would only produce noise.
"""

from app.services.quality.checks.dt_checks import (
    DtCodeMismatch,
    DtFeederMismatch,
    DtWithoutMeters,
    UnknownDt,
)
from app.services.quality.checks.geo_checks import GeoOutlier, MissingGeo
from app.services.quality.checks.hierarchy_checks import (
    BlankFieldRepaired,
    NameConflict,
    ParentConflictCheck,
    UnplacedMeter,
)
from app.services.quality.models import QualityCheck

CHECKS: tuple[QualityCheck, ...] = (
    NameConflict(),
    BlankFieldRepaired(),
    UnplacedMeter(),
    ParentConflictCheck(),
    DtCodeMismatch(),
    UnknownDt(),
    DtWithoutMeters(),
    DtFeederMismatch(),
    MissingGeo(),
    GeoOutlier(),
)
