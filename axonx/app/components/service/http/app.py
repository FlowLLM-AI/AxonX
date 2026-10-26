"""ASGI application factory for the HTTP service."""

import asyncio
import hmac
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastmcp.utilities.lifespan import combine_lifespans
from starlette.datastructures import Headers
from starlette.responses import JSONResponse

from .....client.base import RemoteServiceError
from .....client.config import (
    AXONX_DEFAULT_CONNECT_HOST,
    AXONX_SERVICE_TARGET,
    PROTOCOL_AUTH_HEADER,
    PROTOCOL_AUTH_SCHEME,
    PROTOCOL_CLI_REQUEST_HEADER,
    PROTOCOL_ROUTE_HEALTH,
    PROTOCOL_ROUTE_JOBS,
    PROTOCOL_ROUTE_MCP,
    PROTOCOL_ROUTE_UPLOAD,
    normalize_target,
)
from ....constants import AXONX_DEFAULT_BIND_HOST, AXONX_DEFAULT_ENCODING
from ....core.response import RESPONSE_CALLBACKS
from .files import create_files_router
from .jobs import create_jobs_router, create_mcp_server
from .proxy import create_proxy_router
from .studio import mount_studio, resolve_studio_dir

_AUTH_ROOTS = frozenset({PROTOCOL_ROUTE_UPLOAD, PROTOCOL_ROUTE_HEALTH, PROTOCOL_ROUTE_JOBS, PROTOCOL_ROUTE_MCP})


class _ProtocolAuthMiddleware:
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
                supplied = Headers(scope=scope).get(PROTOCOL_AUTH_HEADER, "").encode(AXONX_DEFAULT_ENCODING)
                if not hmac.compare_digest(supplied, self.expected):
                    response = JSONResponse(
                        status_code=401,
                        content={"detail": "Invalid bearer token"},
                    )
                    await response(scope, receive, send)
                    return
        await self.app(scope, receive, send)


class _UpdateResponseMiddleware:
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


def create_http_app(app, service) -> FastAPI:
    """Assemble the AxonX HTTP protocol and optional Studio UI."""
    public_jobs = {
        name: job for name, job in app.context.jobs.items() if job.is_public(authenticated=service.token is not None)
    }

    @asynccontextmanager
    async def lifespan(_server):
        async with app:
            previous_target = os.environ.get(AXONX_SERVICE_TARGET)
            advertised_host = AXONX_DEFAULT_CONNECT_HOST if service.host == AXONX_DEFAULT_BIND_HOST else service.host
            host = f"[{advertised_host}]" if ":" in advertised_host else advertised_host
            target = normalize_target(f"{host}:{service.port}")
            os.environ[AXONX_SERVICE_TARGET] = target
            service.logger.info(f"Service started: {AXONX_SERVICE_TARGET}={target}")
            if service.token is None:
                service.logger.warning(
                    "The HTTP service is unauthenticated; set service.token before "
                    "exposing it beyond a trusted network",
                )

            async def ready():
                if service.server is None or service.on_ready is None:
                    return
                while not service.server.started:
                    await asyncio.sleep(0.05)
                await service.on_ready()

            readiness = asyncio.create_task(ready())
            try:
                yield
            finally:
                service.request_shutdown()
                readiness.cancel()
                await asyncio.gather(readiness, return_exceptions=True)
                if previous_target is None:
                    os.environ.pop(AXONX_SERVICE_TARGET, None)
                else:
                    os.environ[AXONX_SERVICE_TARGET] = previous_target

    mcp_app = create_mcp_server(app, public_jobs).http_app(
        path=PROTOCOL_ROUTE_MCP,
        transport="streamable-http",
        stateless_http=True,
        json_response=True,
    )
    server = FastAPI(
        title=app.app_config.app_name,
        lifespan=combine_lifespans(lifespan, mcp_app.lifespan),
    )

    @server.exception_handler(RemoteServiceError)
    async def remote_error(_request, exc):
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    server.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    server.add_middleware(_UpdateResponseMiddleware, service=service)
    server.add_middleware(_ProtocolAuthMiddleware, token=service.token)
    server.router.routes.extend(mcp_app.routes)
    server.include_router(create_jobs_router(app, public_jobs))
    server.include_router(create_files_router(service, app.workspace))
    server.include_router(create_proxy_router(app))
    if service.web_enabled:
        static_dir = resolve_studio_dir()
        if static_dir is None:
            service.logger.info("AxonX Studio is unavailable; install axonx-studio to enable it")
        else:
            mount_studio(server, static_dir)
    return server
