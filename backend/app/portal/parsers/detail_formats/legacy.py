"""Legacy detail format: a list of {parameterName, parameterValue} pairs."""

from app.domain.exceptions import UpstreamProtocolError

_LABELS = {
    "Meter ID": "meter_id",
    "Serial No": "serial_no",
    "Make": "make",
    "Phase Type": "phase_type",
    "Installation Status": "install_status",
    "Installation Type": "install_type",
}


class LegacyFormat:
    build = "legacy"

    def matches(self, detail: dict[str, object]) -> bool:
        return isinstance(detail.get("data"), list)

    def fields(self, detail: dict[str, object]) -> dict[str, str]:
        pairs = detail["data"]
        if not isinstance(pairs, list):
            raise UpstreamProtocolError("legacy detail data is not a list")
        by_label: dict[str, str] = {}
        for pair in pairs:
            if not isinstance(pair, dict):
                raise UpstreamProtocolError("legacy detail entry is not an object")
            name, value = pair.get("parameterName"), pair.get("parameterValue")
            if isinstance(name, str) and isinstance(value, str):
                by_label[name] = value
        missing = [label for label in _LABELS if label not in by_label]
        if missing:
            raise UpstreamProtocolError(f"legacy detail lacks {missing}")
        return {canon: by_label[label] for label, canon in _LABELS.items()}
