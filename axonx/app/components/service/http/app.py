"""ASGI application factory for the HTTP service."""

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastmcp.utilities.lifespan import combine_lifespans
from starlette.responses import JSONResponse

from .....client.base import RemoteServiceError
from .....client.config import (
    AXONX_SERVICE_TARGET,
    PROTOCOL_ROUTE_MCP,
)
from .files import create_files_router
from .jobs import create_jobs_router, create_mcp_server
from .middleware import ProtocolAuthMiddleware, ResponseCompletionMiddleware
from .proxy import create_proxy_router
from .studio import mount_studio, resolve_studio_dir


def create_http_app(app, service) -> FastAPI:
    """Assemble the AxonX HTTP protocol and optional Studio UI."""
    public_jobs = {
        name: job for name, job in app.context.jobs.items() if job.is_public(authenticated=service.token is not None)
    }

    @asynccontextmanager
    async def lifespan(_server):
        async with app:
            previous_target = os.environ.get(AXONX_SERVICE_TARGET)
            target = service.local_target
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
    server.add_middleware(ResponseCompletionMiddleware, service=service)
    server.add_middleware(ProtocolAuthMiddleware, token=service.token)
    server.router.routes.extend(mcp_app.routes)
    server.include_router(create_jobs_router(app, public_jobs))
    server.include_router(create_files_router(service, app.workspace.uploads))
    server.include_router(create_proxy_router(app))
    if service.web_enabled:
        static_dir = resolve_studio_dir()
        if static_dir is None:
            service.logger.info("AxonX Studio is unavailable; install axonx-studio to enable it")
        else:
            mount_studio(server, static_dir)
    return server
