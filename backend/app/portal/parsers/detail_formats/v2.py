"""V2 detail format: a JSON string `classData` holding PascalCase `installed_meter`."""

import json

from app.domain.exceptions import UpstreamProtocolError

_KEYS = {
    "MeterId": "meter_id",
    "SerialNo": "serial_no",
    "Make": "make",
    "PhaseType": "phase_type",
    "InstallationStatus": "install_status",
    "InstallationType": "install_type",
}


class V2Format:
    build = "v2"

    def matches(self, detail: dict[str, object]) -> bool:
        return isinstance(detail.get("classData"), str)

    def fields(self, detail: dict[str, object]) -> dict[str, str]:
        class_data = detail["classData"]
        if not isinstance(class_data, str):
            raise UpstreamProtocolError("v2 classData is not a string")
        try:
            meter = json.loads(class_data)["installed_meter"]
        except (ValueError, KeyError, TypeError):
            raise UpstreamProtocolError("v2 classData is not valid") from None
        if not isinstance(meter, dict):
            raise UpstreamProtocolError("v2 installed_meter is not an object")
        out: dict[str, str] = {}
        for key, canon in _KEYS.items():
            value = meter.get(key)
            if not isinstance(value, str):
                raise UpstreamProtocolError(f"v2 installed_meter lacks {key}")
            out[canon] = value
        return out
