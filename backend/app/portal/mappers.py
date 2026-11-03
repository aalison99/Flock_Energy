"""Pure functions that turn plain portal dicts and strings into domain objects."""

import logging
import math
import re
from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from zoneinfo import ZoneInfo

from app.domain.exceptions import UpstreamProtocolError
from app.domain.models import (
    GeoPoint,
    HierarchyPath,
    InstallStatus,
    InstallType,
    Meter,
    NodeRef,
    PhaseType,
    Reading,
    Transformer,
)

logger = logging.getLogger(__name__)

PORTAL_TZ = ZoneInfo("Asia/Kolkata")  # assumption ADR-009: portal timestamps are IST
_NODE_RE = re.compile(r"^(?P<name>.*?)\s*\((?P<code>[^()]*)\)\s*$")
_TS_FORMAT = "%d/%m/%Y %H:%M"


def _blank_to_none(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def parse_node(text: str) -> NodeRef:
    """Split "Name (CODE)" into a NodeRef; blank halves become None."""
    match = _NODE_RE.match(text)
    if match is None:
        return NodeRef(None, _blank_to_none(text))
    return NodeRef(_blank_to_none(match["code"]), _blank_to_none(match["name"]))


def node_from_obj(obj: Mapping[str, object]) -> NodeRef:
    """Build a NodeRef from the export's {"name", "code"} object."""
    return NodeRef(_blank_to_none(obj.get("code")), _blank_to_none(obj.get("name")))


def _normalise[E: StrEnum](enum: type[E], unknown: E, field: str, raw: object) -> E:
    if isinstance(raw, str):
        key = "_".join(raw.strip().lower().split())
        try:
            return enum(key)
        except ValueError:
            pass
    logger.warning("unknown %s value %r; mapping to unknown", field, raw)
    return unknown


def to_phase_type(raw: object) -> PhaseType:
    return _normalise(PhaseType, PhaseType.UNKNOWN, "phase_type", raw)


def to_install_status(raw: object) -> InstallStatus:
    return _normalise(InstallStatus, InstallStatus.UNKNOWN, "install_status", raw)


def to_install_type(raw: object) -> InstallType:
    return _normalise(InstallType, InstallType.UNKNOWN, "install_type", raw)


def _number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, str | int | float):
        raise UpstreamProtocolError(f"field {field} is not a number: {value!r}")
    if isinstance(value, str) and ("_" in value or value != value.strip()):
        raise UpstreamProtocolError(f"field {field} is not a plain number: {value!r}")
    try:
        number = float(value)
    except (ValueError, OverflowError):
        raise UpstreamProtocolError(f"field {field} is not a usable number") from None
    if not math.isfinite(number):
        raise UpstreamProtocolError(f"field {field} is not finite")
    return number


def to_float(value: object, *, field: str) -> float:
    """Parse a required str/int/float number; anything else is an UpstreamProtocolError."""
    if value is None or (isinstance(value, str) and not value.strip()):
        raise UpstreamProtocolError(f"missing numeric field {field}")
    return _number(value, field)


def to_optional_float(value: object, *, field: str) -> float | None:
    """Like to_float, but None or a blank string gives None."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return _number(value, field)


def parse_timestamp(value: object) -> datetime:
    """Parse "dd/mm/yyyy HH:MM" as an Asia/Kolkata-aware datetime."""
    if not isinstance(value, str):
        raise UpstreamProtocolError(f"timestamp is not a string: {value!r}")
    try:
        return datetime.strptime(value.strip(), _TS_FORMAT).replace(tzinfo=PORTAL_TZ)
    except ValueError:
        raise UpstreamProtocolError(f"bad timestamp {value!r}, expected dd/mm/yyyy HH:MM") from None


def req_str(data: Mapping[str, object], key: str) -> str:
    """Return a required, stripped string field."""
    value = data.get(key)
    if not isinstance(value, str):
        raise UpstreamProtocolError(f"missing or non-string field {key}")
    return value.strip()


def _opt_str(data: Mapping[str, object], key: str) -> str | None:
    return _blank_to_none(data.get(key))


def meter_from_summary(d: Mapping[str, object]) -> Meter:
    """A search-result row: no install type, build, hierarchy or geo."""
    return Meter(
        meter_id=req_str(d, "meterId"),
        serial_no=req_str(d, "serialNo"),
        make=req_str(d, "make"),
        phase_type=to_phase_type(d.get("phaseType")),
        install_status=to_install_status(d.get("installStatus")),
        install_type=None,
        build=None,
        dt_code=_opt_str(d, "dtCode"),
        hierarchy=None,
        geo=None,
    )


_LEVELS = ("zone", "circle", "division", "subdivision", "substation", "feeder", "dt")


def meter_from_export(d: Mapping[str, object]) -> Meter:
    """A full export record, including hierarchy and geo."""
    raw_h = d.get("hierarchy")
    raw_geo = d.get("geo")
    if not isinstance(raw_h, dict) or not isinstance(raw_geo, dict):
        raise UpstreamProtocolError("export record lacks hierarchy or geo object")
    nodes: dict[str, NodeRef] = {}
    for level in _LEVELS:
        obj = raw_h.get(level)
        if not isinstance(obj, dict):
            raise UpstreamProtocolError(f"export hierarchy lacks level {level}")
        nodes[level] = node_from_obj(obj)
    lat = to_float(raw_geo.get("lat"), field="geo.lat")
    lng = to_float(raw_geo.get("lng"), field="geo.lng")
    return Meter(
        meter_id=req_str(d, "meterId"),
        serial_no=req_str(d, "serialNo"),
        make=req_str(d, "make"),
        phase_type=to_phase_type(d.get("phaseType")),
        install_status=to_install_status(d.get("installStatus")),
        install_type=to_install_type(d.get("installType")),
        build=_opt_str(d, "build"),
        dt_code=_opt_str(d, "dtCode") or nodes["dt"].code,
        hierarchy=HierarchyPath(**nodes),
        geo=_geo(lat, lng),
    )


def meter_from_detail(
    fields: Mapping[str, str], hierarchy: Mapping[str, object], build: str
) -> Meter:
    """A route-data detail: canonical nameplate fields plus the "Name (CODE)" hierarchy map."""
    labels = {
        "zone": "Zone",
        "circle": "Circle",
        "division": "Division",
        "subdivision": "Subdivision",
        "substation": "Sub Station",
        "feeder": "Feeder",
        "dt": "DT",
    }
    nodes: dict[str, NodeRef] = {}
    for level, label in labels.items():
        text = hierarchy.get(label)
        if not isinstance(text, str):
            raise UpstreamProtocolError(f"detail hierarchy lacks {label}")
        nodes[level] = parse_node(text)
    return Meter(
        meter_id=req_str(fields, "meter_id"),
        serial_no=req_str(fields, "serial_no"),
        make=req_str(fields, "make"),
        phase_type=to_phase_type(fields.get("phase_type")),
        install_status=to_install_status(fields.get("install_status")),
        install_type=to_install_type(fields.get("install_type")),
        build=build,
        dt_code=nodes["dt"].code,
        hierarchy=HierarchyPath(**nodes),
        geo=None,
    )


def _geo(lat: float, lng: float) -> GeoPoint:
    try:
        return GeoPoint(lat, lng)
    except ValueError as exc:
        raise UpstreamProtocolError(str(exc)) from None


def geo_from_strings(lat: object, lng: object) -> GeoPoint:
    return _geo(to_float(lat, field="latitude"), to_float(lng, field="longitude"))


def transformer_from_dict(d: Mapping[str, object]) -> Transformer:
    capacity = to_float(d.get("capacityKva"), field="capacityKva")
    if not capacity.is_integer():
        raise UpstreamProtocolError(f"capacityKva is not a whole number: {capacity}")
    return Transformer(
        code=req_str(d, "code"),
        name=req_str(d, "name"),
        feeder_code=_opt_str(d, "feederCode"),
        capacity_kva=int(capacity),
    )


def reading_from_dict(d: Mapping[str, object]) -> Reading:
    kwh = to_float(d.get("kwh"), field="kwh")
    kvah = to_float(d.get("kvah"), field="kvah")
    return Reading(
        at=parse_timestamp(d.get("timestamp")),
        kwh_register=kwh,
        kvah_register=kvah,
        voltage_r=to_optional_float(d.get("voltR"), field="voltR"),
    )
