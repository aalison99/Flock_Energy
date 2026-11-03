"""Pure ASGI middleware: request-id propagation and one access-log line per request."""

import logging
import re
import time
import uuid

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
access_logger = logging.getLogger("urja.access")


class RequestContextMiddleware:
    """Assigns a request id, echoes it in the response and logs the request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = Headers(scope=scope).get(REQUEST_ID_HEADER, "")
        request_id = incoming if _VALID_ID.match(incoming) else uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        start = time.perf_counter()
        status = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            access_logger.info(
                "%s %s %s %.2fms rid=%s",
                scope["method"],
                scope["path"],
                status,
                duration_ms,
                request_id,
                extra={
                    "method": scope["method"],
                    "path": scope["path"],
                    "status": status,
                    "duration_ms": duration_ms,
                    "request_id": request_id,
                },
            )
