"""FastAPI and MCP service component for remotely callable jobs."""

import json
import os
from contextlib import asynccontextmanager

from ...constants import AXONX_DEFAULT_HOST, AXONX_DEFAULT_PORT, AXONX_SERVICE_INFO
from ...schema import JobInfo, Response
from .base_service import BaseService
from ..component_registry import R


@R.register("http")
class HttpService(BaseService):
    """Expose public jobs over REST and Streamable HTTP MCP."""

    def __init__(
        self,
        host=AXONX_DEFAULT_HOST,
        port=AXONX_DEFAULT_PORT,
        shutdown_timeout=1.0,
        **kwargs,
    ):
        super().__init__(**kwargs)
        if shutdown_timeout < 0:
            raise ValueError("shutdown_timeout must be non-negative")
        self.host, self.port = host, port
        self.shutdown_timeout = shutdown_timeout
        self.mcp_server = None

    def _add_mcp_job(self, app, job):
        from fastmcp.tools import FunctionTool

        async def execute_tool(**arguments) -> Response:
            return await app.run_job(job.name, **arguments)

        self.mcp_server.add_tool(
            FunctionTool(
                name=job.name,
                description=job.description,
                parameters=job.parameters,
                output_schema=Response.model_json_schema(),
                fn=execute_tool,
                return_type=Response,
            ),
        )

    def build_service(self, app):
        """Build the ASGI application without starting a server."""
        from fastapi import FastAPI, HTTPException
        from fastmcp import FastMCP
        from fastmcp.utilities.lifespan import combine_lifespans
        from starlette.routing import Route

        public_jobs = {name: job for name, job in app.context.jobs.items() if job.is_servable}

        @asynccontextmanager
        async def lifespan(_server):
            async with app:
                previous_service_info = os.environ.get(AXONX_SERVICE_INFO)
                service_info = json.dumps({"host": self.host, "port": self.port})
                os.environ[AXONX_SERVICE_INFO] = service_info
                self.logger.info(
                    f"Service started: {AXONX_SERVICE_INFO}={service_info}",
                )
                try:
                    yield
                finally:
                    if previous_service_info is None:
                        os.environ.pop(AXONX_SERVICE_INFO, None)
                    else:
                        os.environ[AXONX_SERVICE_INFO] = previous_service_info

        self.mcp_server = FastMCP(name=app.config.app_name)
        for job in public_jobs.values():
            self._add_mcp_job(app, job)
        mcp_app = self.mcp_server.http_app(path="/mcp", transport="streamable-http")

        server = FastAPI(
            title=app.config.app_name,
            lifespan=combine_lifespans(lifespan, mcp_app.lifespan),
        )
        server.router.routes.append(
            Route("/mcp", endpoint=mcp_app, include_in_schema=False),
        )

        @server.get("/health")
        async def health():
            return {"running": app.is_started}

        @server.get("/jobs", response_model=list[JobInfo])
        async def list_jobs():
            return [job.info for job in public_jobs.values()]

        @server.post("/jobs/{name}", response_model=Response)
        async def run_job(name: str, arguments: dict):
            if name not in public_jobs:
                raise HTTPException(404, "Unknown job")
            try:
                response = await app.run_job(name, **arguments)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            return response

        return server

    def run_app(self, app):
        """Serve the application with Uvicorn until shutdown."""
        import uvicorn

        uvicorn.run(
            self.build_service(app),
            host=self.host,
            port=self.port,
            timeout_graceful_shutdown=self.shutdown_timeout,
        )
