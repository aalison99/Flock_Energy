"""Domain exceptions: the vocabulary of failures every layer raises and the API translates.

Stdlib only; each carries a stable machine-readable `code`.
"""


class DomainError(Exception):
    """Base class for all expected, translatable failures."""

    code: str = "domain_error"

    def __init__(self, message: str, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict[str, object] = details if details is not None else {}


class ValidationError(DomainError):
    code = "validation_error"


class FilterRequiresIndexError(ValidationError):
    """A filter or sort the live portal cannot serve; only the local index can."""


class NotFoundError(DomainError):
    code = "not_found"


class ConflictError(DomainError):
    code = "conflict"


class IndexNotReadyError(DomainError):
    code = "index_not_ready"


class UpstreamAuthError(DomainError):
    code = "upstream_auth_failed"


class UpstreamProtocolError(DomainError):
    code = "upstream_protocol_error"


class UpstreamUnavailableError(DomainError):
    code = "upstream_unavailable"

    def __init__(
        self,
        message: str,
        details: dict[str, object] | None = None,
        retry_after_s: int | None = None,
    ) -> None:
        super().__init__(message, details)
        self.retry_after_s = retry_after_s
