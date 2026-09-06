"""Small request-shape boundary for unsafe browser methods."""

from collections.abc import Awaitable, Callable
from typing import Any

from starlette.responses import JSONResponse
from starlette.types import Message, Receive, Scope, Send


MAX_UNSAFE_REQUEST_BODY_BYTES = 4096
_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class UnsafeRequestBoundaryMiddleware:
    """Reject cross-origin or oversized mutations before route dependencies."""

    def __init__(self, app: Callable[..., Awaitable[None]], *, origin: str) -> None:
        self.app = app
        self.origin = origin.encode("ascii")

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http" or scope["method"] not in _UNSAFE_METHODS:
            await self.app(scope, receive, send)
            return

        headers = {name.lower(): value for name, value in scope["headers"]}
        supplied_origin = headers.get(b"origin")
        if supplied_origin is not None and supplied_origin != self.origin:
            await JSONResponse(
                status_code=403,
                content={"detail": "Request origin is not allowed."},
            )(scope, receive, send)
            return

        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                declared_length = int(content_length)
            except ValueError:
                declared_length = MAX_UNSAFE_REQUEST_BODY_BYTES + 1
            if declared_length > MAX_UNSAFE_REQUEST_BODY_BYTES:
                await self._too_large(scope, receive, send)
                return

        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > MAX_UNSAFE_REQUEST_BODY_BYTES:
                await self._too_large(scope, receive, send)
                return
            if not message.get("more_body", False):
                break

        delivered = False

        async def replay_body() -> Message:
            nonlocal delivered
            if delivered:
                return {"type": "http.request", "body": b"", "more_body": False}
            delivered = True
            return {
                "type": "http.request",
                "body": bytes(body),
                "more_body": False,
            }

        await self.app(scope, replay_body, send)

    @staticmethod
    async def _too_large(scope: Scope, receive: Receive, send: Send) -> None:
        await JSONResponse(
            status_code=413,
            content={"detail": "Request body is too large."},
        )(scope, receive, send)
