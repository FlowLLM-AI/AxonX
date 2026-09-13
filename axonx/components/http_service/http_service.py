"""FastAPI and MCP service component for remotely callable jobs."""

import asyncio
import hmac
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from ...constants import (
    AXONX_DEFAULT_BIND_HOST,
    AXONX_DEFAULT_CONNECT_HOST,
    AXONX_DEFAULT_PORT,
    AXONX_SERVICE_INFO,
)
from ...schema import JobInfo, Response
from ...utils import format_log_arguments
from ..component_registry import R
from .base_service import BaseService


@R.register("http")
class HttpService(BaseService):
    """Expose public jobs over REST and Streamable HTTP MCP."""

    def __init__(
        self,
        host: str = AXONX_DEFAULT_BIND_HOST,
        port: int = AXONX_DEFAULT_PORT,
        shutdown_timeout: int = 1,
        web_enabled: bool = True,
        web_static_dir: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        if shutdown_timeout < 0:
            raise ValueError("shutdown_timeout must be non-negative")
        self.host, self.port = host, port
        self.shutdown_timeout = shutdown_timeout
        self.web_enabled = web_enabled
        self.web_static_dir = web_static_dir
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
        from fastapi import FastAPI, HTTPException, Request
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import FileResponse
        from fastapi.staticfiles import StaticFiles
        from fastmcp import FastMCP
        from fastmcp.utilities.lifespan import combine_lifespans
        from starlette.routing import Route

        public_jobs = {name: job for name, job in app.context.jobs.items() if job.is_servable}

        @asynccontextmanager
        async def lifespan(_server):
            async with app:
                previous_service_info = os.environ.get(AXONX_SERVICE_INFO)
                advertised_host = AXONX_DEFAULT_CONNECT_HOST if self.host == AXONX_DEFAULT_BIND_HOST else self.host
                service_info = json.dumps({"host": advertised_host, "port": self.port})
                os.environ[AXONX_SERVICE_INFO] = service_info
                self.logger.info(f"Service started: {AXONX_SERVICE_INFO}={service_info}")
                try:
                    yield
                finally:
                    if previous_service_info is None:
                        os.environ.pop(AXONX_SERVICE_INFO, None)
                    else:
                        os.environ[AXONX_SERVICE_INFO] = previous_service_info

        self.mcp_server = FastMCP(name=app.app_config.app_name)
        for job in public_jobs.values():
            self._add_mcp_job(app, job)
        mcp_app = self.mcp_server.http_app(path="/mcp", transport="streamable-http")

        server = FastAPI(
            title=app.app_config.app_name,
            lifespan=combine_lifespans(lifespan, mcp_app.lifespan),
        )
        server.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        server.router.routes.append(Route("/mcp", endpoint=mcp_app, include_in_schema=False))

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

        @server.post("/plugins")
        async def install_plugin(request: Request):
            arguments = format_log_arguments(
                {
                    "filename": request.headers.get("x-wheel-filename", ""),
                    "sha256": request.headers.get("x-wheel-sha256", ""),
                    "content_length": request.headers.get("content-length", ""),
                },
            )
            self.logger.info(f"Plugin endpoint called: name=install_plugin arguments={arguments}")
            plugins = app.context.components.get("plugin", {})
            plugin = next(iter(plugins.values()), None)
            if plugin is None:
                raise HTTPException(404, "Plugin component is not configured")
            if not plugin.allow_remote_install:
                raise HTTPException(403, "Remote plugin installation is disabled")
            authorization = request.headers.get("authorization", "")
            if plugin.install_token and not hmac.compare_digest(
                authorization,
                f"Bearer {plugin.install_token}",
            ):
                raise HTTPException(401, "Invalid plugin installation token")
            content_length = request.headers.get("content-length")
            if content_length and int(content_length) > plugin.max_wheel_bytes:
                raise HTTPException(413, "Wheel exceeds configured size limit")
            data = await request.body()
            try:
                artifact = await asyncio.to_thread(
                    plugin.install_wheel,
                    data,
                    request.headers.get("x-wheel-sha256", ""),
                    request.headers.get("x-wheel-filename", ""),
                )
            except (RuntimeError, TypeError, ValueError) as exc:
                raise HTTPException(422, str(exc)) from exc
            return {
                "installed": True,
                "distribution": artifact.distribution,
                "version": artifact.version,
                "plugins": artifact.plugin_names,
                **artifact.contributions_dict(),
                "restart_required": bool(artifact.components or artifact.jobs),
                "sha256": artifact.sha256,
            }

        for job in app.context.jobs.values():
            job.mount_http_routes(server)

        self._mount_web_app(server, StaticFiles, FileResponse, HTTPException)

        return server

    def _mount_web_app(self, server, static_files, file_response, http_exception) -> None:
        """Serve the optional AxonX Studio static build as a same-origin SPA."""
        if not self.web_enabled:
            return
        static_dir = self._resolve_web_static_dir()
        if static_dir is None:
            self.logger.info("AxonX Studio is unavailable; no static build was found")
            return

        assets_dir = static_dir / "assets"
        if assets_dir.is_dir():
            server.mount("/assets", static_files(directory=str(assets_dir)), name="web-assets")
        index_file = static_dir / "index.html"
        no_cache_headers = {"Cache-Control": "no-cache, no-store, must-revalidate"}

        @server.get("/{full_path:path}", include_in_schema=False)
        async def studio_spa(full_path: str):
            if full_path in {"docs", "redoc", "openapi.json"}:
                raise http_exception(status_code=404, detail="Not Found")
            if full_path and not Path(full_path).is_absolute():
                static_file = (static_dir / full_path).resolve()
                if static_file.is_relative_to(static_dir) and static_file.is_file():
                    return file_response(static_file)
            return file_response(index_file, headers=no_cache_headers)

    def _resolve_web_static_dir(self) -> Path | None:
        candidates = []
        if self.web_static_dir:
            candidates.append(Path(self.web_static_dir).expanduser())
        candidates.extend(
            (
                Path(__file__).resolve().parents[3] / "axon_studio" / "dist",
                Path(__file__).resolve().parents[2] / "static",
            ),
        )
        for candidate in candidates:
            resolved = candidate.resolve()
            if (resolved / "index.html").is_file():
                return resolved
        return None

    def run_app(self, app):
        """Serve the application with Uvicorn until shutdown."""
        import uvicorn

        uvicorn.run(
            self.build_service(app),
            host=self.host,
            port=self.port,
            timeout_graceful_shutdown=self.shutdown_timeout,
        )
