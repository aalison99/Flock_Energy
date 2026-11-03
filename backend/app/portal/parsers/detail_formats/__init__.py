"""Sub-registry of meter-detail formats; adding a format is one class plus one register call."""

from typing import Protocol

from app.domain.exceptions import UpstreamProtocolError


class DetailFormat(Protocol):
    """Reads the nameplate out of one shape of the detail object."""

    build: str

    def matches(self, detail: dict[str, object]) -> bool: ...

    def fields(self, detail: dict[str, object]) -> dict[str, str]:
        """Canonical keys: meter_id, serial_no, make, phase_type, install_status, install_type."""
        ...


class DetailFormatRegistry:
    """Ordered collection of formats; the first that matches wins."""

    def __init__(self) -> None:
        self._formats: list[DetailFormat] = []

    def register(self, fmt: DetailFormat) -> None:
        if any(f.build == fmt.build for f in self._formats):
            raise ValueError(f"detail format already registered: {fmt.build}")
        self._formats.append(fmt)

    def resolve(self, detail: dict[str, object]) -> tuple[DetailFormat, dict[str, str]]:
        for fmt in self._formats:
            if fmt.matches(detail):
                return fmt, fmt.fields(detail)
        raise UpstreamProtocolError(f"METER_DETAIL: unknown detail format, keys={sorted(detail)}")


def default_detail_formats() -> DetailFormatRegistry:
    """A registry with the legacy and v2 formats."""
    from app.portal.parsers.detail_formats.legacy import LegacyFormat
    from app.portal.parsers.detail_formats.v2 import V2Format

    registry = DetailFormatRegistry()
    registry.register(LegacyFormat())
    registry.register(V2Format())
    return registry
