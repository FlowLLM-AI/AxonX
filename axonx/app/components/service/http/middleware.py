"""HTTP protocol authentication and response-completion policy boundaries."""

import hmac

from starlette.datastructures import Headers
from starlette.responses import JSONResponse

from .....client.config import (
    PROTOCOL_AUTH_HEADER,
    PROTOCOL_AUTH_SCHEME,
    PROTOCOL_CLI_REQUEST_HEADER,
    PROTOCOL_ROUTE_HEALTH,
    PROTOCOL_ROUTE_JOBS,
    PROTOCOL_ROUTE_MCP,
    PROTOCOL_ROUTE_UPLOAD,
)
from ...job.base import RESPONSE_CALLBACKS

_AUTH_ROOTS = frozenset(
    {
        PROTOCOL_ROUTE_UPLOAD,
        PROTOCOL_ROUTE_HEALTH,
        PROTOCOL_ROUTE_JOBS,
        PROTOCOL_ROUTE_MCP,
    }
)


class ProtocolAuthMiddleware:
    """Apply one bearer token to every AxonX protocol transport."""

    def __init__(self, app, token: str | None) -> None:
        self.app = app
        self.expected = f"{PROTOCOL_AUTH_SCHEME} {token}".encode() if token is not None else None

    async def __call__(self, scope, receive, send) -> None:
        if self.expected is not None and scope["type"] == "http":
            method = scope.get("method", "")
            path = scope.get("path", "")
            protected = path in _AUTH_ROOTS or any(path.startswith(f"{root}/") for root in _AUTH_ROOTS)
            if method != "OPTIONS" and protected:
                supplied = Headers(scope=scope).get(PROTOCOL_AUTH_HEADER, "").encode()
                if not hmac.compare_digest(supplied, self.expected):
                    response = JSONResponse(
                        status_code=401,
                        content={"detail": "Invalid bearer token"},
                    )
                    await response(scope, receive, send)
                    return
        await self.app(scope, receive, send)


class ResponseCompletionMiddleware:
    """Handoff only when the invoking HTTP/MCP response has finished sending."""

    def __init__(self, app, service) -> None:
        self.app = app
        self.service = service

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request_id = Headers(scope=scope).get(PROTOCOL_CLI_REQUEST_HEADER)
        parent_callbacks = self.service.cli_callbacks.get(request_id)
        callbacks = parent_callbacks if parent_callbacks is not None else []
        token = RESPONSE_CALLBACKS.set(callbacks)
        completed = False

        async def send_response(message):
            nonlocal completed
            await send(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                completed = True

        try:
            await self.app(scope, receive, send_response)
        finally:
            RESPONSE_CALLBACKS.reset(token)
            if parent_callbacks is None and completed:
                for callback in callbacks:
                    callback()
