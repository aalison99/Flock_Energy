"""Shared parser skeleton: JSON load, portal error signals, and protocol-error wrapping."""

import json
import logging
from collections.abc import Callable, Mapping

from app.domain.exceptions import DomainError, NotFoundError, UpstreamProtocolError
from app.domain.models import Meter
from app.portal.errors import SessionExpired, SignatureRejected
from app.portal.interfaces import PortalPage
from app.portal.parsers.registry import PayloadKind

logger = logging.getLogger(__name__)


def _unauthorized(_message: str) -> Exception:
    return SessionExpired("portal reports unauthorized")


def _not_found(message: str) -> Exception:
    return NotFoundError(message)


def _signature(_message: str) -> Exception:
    return SignatureRejected("portal rejected the request signature")


_ERROR_SIGNALS: dict[str, Callable[[str], Exception]] = {
    "unauthorized": _unauthorized,
    "not_found": _not_found,
    "signature_invalid": _signature,
}


class JsonParser:
    """Template: load JSON object, check signals, build; any shape problem is a protocol error."""

    kind: PayloadKind

    def parse(self, raw: bytes) -> object:
        try:
            body = json.loads(raw)
            if not isinstance(body, dict):
                raise UpstreamProtocolError("body is not a JSON object")
            self.check_signals(body)
            return self.build(body)
        except UpstreamProtocolError as exc:
            raise self._wrap(exc.message) from None
        except (DomainError, SessionExpired, SignatureRejected):
            raise  # our own signals
        except KeyError as exc:
            raise self._wrap(f"missing key {exc}") from None
        except Exception as exc:  # the guarantee: only our own exceptions leave a parser
            logger.warning("unexpected error parsing %s", self.kind.name, exc_info=True)
            raise self._wrap(f"unexpected shape ({type(exc).__name__})") from None

    def _wrap(self, message: str) -> UpstreamProtocolError:
        prefix = f"{self.kind.name}: "
        return UpstreamProtocolError(message if message.startswith(prefix) else prefix + message)

    def check_signals(self, body: dict[str, object]) -> None:
        """Raise the signal for a portal `{"error": ...}` body; subclasses may add more."""
        factory = _ERROR_SIGNALS.get(str(body.get("error")))
        if factory is not None:
            raise factory(str(body.get("message", "")))

    def build(self, body: dict[str, object]) -> object:
        raise NotImplementedError


def rows(value: object) -> list[Mapping[str, object]]:
    """Require a list of JSON objects."""
    if not isinstance(value, list) or not all(isinstance(r, dict) for r in value):
        raise UpstreamProtocolError("expected a list of objects")
    return value


def require_int(body: Mapping[str, object], key: str) -> int:
    value = body[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise UpstreamProtocolError(f"{key} is not an integer")
    return value


def paged[T](
    body: Mapping[str, object], build: Callable[[Mapping[str, object]], T]
) -> PortalPage[T]:
    """Map the `{data,total,page,pageSize}` envelope."""
    return PortalPage(
        items=tuple(build(r) for r in rows(body["data"])),
        total=require_int(body, "total"),
        page=require_int(body, "page"),
        page_size=require_int(body, "pageSize"),
    )


def meters(value: object, build: Callable[[Mapping[str, object]], Meter]) -> list[Meter]:
    return [build(r) for r in rows(value)]
