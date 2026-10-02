"""ASGI application factory for the HTTP service."""

import os
import hmac
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastmcp.utilities.lifespan import combine_lifespans
from starlette.datastructures import Headers
from starlette.responses import JSONResponse

from ....constants import (
    AXONX_DEFAULT_BIND_HOST,
    AXONX_DEFAULT_CONNECT_HOST,
    AXONX_DEFAULT_ENCODING,
    AXONX_SERVICE_TARGET,
    PROTOCOL_AUTH_HEADER,
    PROTOCOL_AUTH_ROOTS,
    PROTOCOL_AUTH_SCHEME,
    PROTOCOL_ROUTE_MCP,
)
from ....utils.target import normalize_target
from ...client.base import RemoteServiceError
from .files import create_files_router
from .jobs import create_jobs_router, create_mcp_server
from .proxy import create_proxy_router
from .studio import mount_studio, resolve_studio_dir


class _ProtocolAuthMiddleware:
    """Apply one bearer token to every AxonX protocol transport."""

    def __init__(self, app, token: str | None) -> None:
        self.app = app
        self.expected = f"{PROTOCOL_AUTH_SCHEME} {token}".encode() if token is not None else None

    async def __call__(self, scope, receive, send) -> None:
        if self.expected is not None and scope["type"] == "http":
            method = scope.get("method", "")
            path = scope.get("path", "")
            protected = path in PROTOCOL_AUTH_ROOTS or any(path.startswith(f"{root}/") for root in PROTOCOL_AUTH_ROOTS)
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


def create_http_app(app, service) -> FastAPI:
    """Assemble the AxonX HTTP protocol and optional Studio UI."""
    public_jobs = {
        name: job
        for name, job in app.context.jobs.items()
        if job.is_servable and (service.token is not None or not job.requires_auth)
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
            try:
                yield
            finally:
                if previous_target is None:
                    os.environ.pop(AXONX_SERVICE_TARGET, None)
                else:
                    os.environ[AXONX_SERVICE_TARGET] = previous_target

    mcp_app = create_mcp_server(app, public_jobs).http_app(
        path=PROTOCOL_ROUTE_MCP,
        transport="streamable-http",
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
    server.add_middleware(_ProtocolAuthMiddleware, token=service.token)
    server.router.routes.extend(mcp_app.routes)
    server.include_router(create_jobs_router(app, public_jobs))
    server.include_router(create_files_router(service, service.staged_files))
    server.include_router(create_proxy_router(app))
    if service.web_enabled:
        static_dir = resolve_studio_dir(service.web_static_dir)
        if static_dir is None:
            service.logger.info("AxonX Studio is unavailable; no static build was found")
        else:
            mount_studio(server, static_dir)
    return server
