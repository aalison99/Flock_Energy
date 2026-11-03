"""Parser for the login form action reply: None on success, UpstreamAuthError on failure."""

from app.domain.exceptions import UpstreamAuthError, UpstreamProtocolError
from app.portal.devalue import decode_string
from app.portal.parsers.base import JsonParser
from app.portal.parsers.registry import PayloadKind


class LoginActionParser(JsonParser):
    kind = PayloadKind.LOGIN_ACTION

    def check_signals(self, body: dict[str, object]) -> None:
        """Login replies use SvelteKit action types, not the `/portal` error shape."""

    def build(self, body: dict[str, object]) -> object:
        outcome = body["type"]
        if outcome == "redirect":
            return None
        if outcome == "failure":
            data = body["data"]
            if not isinstance(data, str):
                raise UpstreamProtocolError("failure data is not a string")
            decoded = decode_string(data)
            if not isinstance(decoded, dict) or not isinstance(decoded["error"], str):
                raise UpstreamProtocolError("failure data has no error string")
            raise UpstreamAuthError(decoded["error"])
        raise UpstreamProtocolError(f"unexpected action type {outcome!r}")
