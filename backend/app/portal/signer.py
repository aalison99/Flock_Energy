"""Builds the HMAC-SHA256 headers the portal requires on signed requests."""

import hashlib
import hmac
from typing import Protocol


class RequestSigner(Protocol):
    def sign(
        self, method: str, path: str, query: str, secret: str, timestamp: int
    ) -> dict[str, str]: ...


class HmacSha256Signer:
    """Signs `method\\npath\\nquery\\ntimestamp` with the portal's signing secret."""

    def sign(
        self, method: str, path: str, query: str, secret: str, timestamp: int
    ) -> dict[str, str]:
        message = "\n".join([method, path, query, str(timestamp)])
        digest = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
        return {"x-timestamp": str(timestamp), "x-signature": digest}
