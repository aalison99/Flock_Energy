"""Parser for the signing-key endpoint; returns the secret string."""

from app.domain.exceptions import UpstreamProtocolError
from app.portal.parsers.base import JsonParser
from app.portal.parsers.registry import PayloadKind


class KeysParser(JsonParser):
    kind = PayloadKind.KEYS

    def build(self, body: dict[str, object]) -> object:
        data = body["data"]
        if not isinstance(data, dict):
            raise UpstreamProtocolError("data is not an object")
        secret = data["signingSecret"]
        if not isinstance(secret, str) or not secret:
            raise UpstreamProtocolError("signingSecret is not a non-empty string")
        return secret
