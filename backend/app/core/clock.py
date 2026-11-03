"""The real Clock implementation backed by the system time."""

from datetime import UTC, datetime


class SystemClock:
    """Returns the current UTC time."""

    def now(self) -> datetime:
        return datetime.now(UTC)
