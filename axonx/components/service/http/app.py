"""ASGI application factory for the HTTP service."""

import json
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastmcp.utilities.lifespan import combine_lifespans
from starlette.routing import Route

from ....constants import AXONX_DEFAULT_BIND_HOST, AXONX_DEFAULT_CONNECT_HOST, AXONX_SERVICE_INFO
from .jobs import create_jobs_router
from .mcp import create_mcp_server
from .plugins import create_plugins_router
from .static import mount_web_app, resolve_web_static_dir


def create_http_app(app, service) -> FastAPI:
    """Assemble HTTP, MCP, mounted Job routes, and optional Studio UI."""
    public_jobs = {name: job for name, job in app.context.jobs.items() if job.is_servable}

    @asynccontextmanager
    async def lifespan(_server):
        async with app:
            previous_service_info = os.environ.get(AXONX_SERVICE_INFO)
            advertised_host = AXONX_DEFAULT_CONNECT_HOST if service.host == AXONX_DEFAULT_BIND_HOST else service.host
            service_info = json.dumps({"host": advertised_host, "port": service.port})
            os.environ[AXONX_SERVICE_INFO] = service_info
            service.logger.info(f"Service started: {AXONX_SERVICE_INFO}={service_info}")
            try:
                yield
            finally:
                if previous_service_info is None:
                    os.environ.pop(AXONX_SERVICE_INFO, None)
                else:
                    os.environ[AXONX_SERVICE_INFO] = previous_service_info

    service.mcp_server = create_mcp_server(app, public_jobs)
    mcp_app = service.mcp_server.http_app(path="/mcp", transport="streamable-http")
    server = FastAPI(title=app.app_config.app_name, lifespan=combine_lifespans(lifespan, mcp_app.lifespan))
    server.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    server.router.routes.append(Route("/mcp", endpoint=mcp_app, include_in_schema=False))
    server.include_router(create_jobs_router(app, public_jobs))
    server.include_router(create_plugins_router(app, service.logger))
    for job in app.context.jobs.values():
        job.mount_http_routes(server)
    if service.web_enabled:
        static_dir = resolve_web_static_dir(service.web_static_dir)
        if static_dir is None:
            service.logger.info("AxonX Studio is unavailable; no static build was found")
        else:
            mount_web_app(server, static_dir)
    return server
