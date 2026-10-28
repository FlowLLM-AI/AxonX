"""HTTP service component backed by FastAPI and Uvicorn."""

import asyncio
import math
import os
import signal
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from functools import partial
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastmcp.utilities.lifespan import combine_lifespans
from starlette.responses import JSONResponse

from .....client.base import RemoteServiceError
from .....client.config import (
    AXONX_DEFAULT_CONNECT_HOST,
    AXONX_DEFAULT_PORT,
    AXONX_SERVICE_TARGET,
    PROTOCOL_ROUTE_MCP,
    normalize_target,
)
from ...registry import provider
from ..base import BaseService
from .files import FileRoutes
from .jobs import JobRoutes
from .middleware import ProtocolAuthMiddleware, ResponseCompletionMiddleware
from .proxy import create_proxy_router
from .studio import mount_studio, resolve_studio_dir

if TYPE_CHECKING:
    from ....core.application import Application


@provider("http")
class HttpService(BaseService):
    """Expose ordinary Jobs over JSON and MCP, plus events and file transfer."""

    def __init__(
        self,
        host: str | None = None,
        port: int = AXONX_DEFAULT_PORT,
        shutdown_timeout: int = 1,
        web_enabled: bool = True,
        token: str | None = None,
        cleanup_timeout: float = 15,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        if shutdown_timeout < 0:
            raise ValueError("shutdown_timeout must be non-negative")
        if not math.isfinite(cleanup_timeout) or cleanup_timeout <= 0:
            raise ValueError("cleanup_timeout must be finite and positive")
        if token is not None and (not isinstance(token, str) or not token):
            raise ValueError("token must be a non-empty string")
        self.host = host or self.app_config.bind_host
        self.port = port
        self.shutdown_timeout = shutdown_timeout
        self.cleanup_timeout = cleanup_timeout
        self._shutdown_deadline = None
        self.web_enabled = web_enabled
        self.token = token
        self.server = None
        self.on_ready: Callable[[], Awaitable[None]] | None = None
        self.cli_processes: set[int] = set()
        self.cli_callbacks: dict[str, list[Callable[[], None]] | None] = {}

    @property
    def local_target(self) -> str:
        """Return the canonical address used by this service's local child processes."""
        host = AXONX_DEFAULT_CONNECT_HOST if self.host == "0.0.0.0" else self.host
        host = f"[{host}]" if ":" in host else host
        return normalize_target(f"{host}:{self.port}")

    def build_service(self, app: "Application") -> FastAPI:
        """Assemble the AxonX HTTP protocol and optional Studio UI."""
        jobs = JobRoutes(app, authenticated=self.token is not None)
        mcp_app = jobs.create_mcp_server().http_app(
            path=PROTOCOL_ROUTE_MCP,
            transport="streamable-http",
            stateless_http=True,
            json_response=True,
        )
        server = FastAPI(
            title=app.app_config.app_name,
            lifespan=combine_lifespans(partial(self._lifespan, app), mcp_app.lifespan),
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
        server.add_middleware(ResponseCompletionMiddleware, service=self)
        server.add_middleware(ProtocolAuthMiddleware, token=self.token)
        server.router.routes.extend(mcp_app.routes)
        server.include_router(jobs)
        server.include_router(FileRoutes(self, app.workspace.uploads))
        server.include_router(create_proxy_router(app))
        if self.web_enabled:
            static_dir = resolve_studio_dir()
            if static_dir is None:
                self.logger.info("AxonX Studio is unavailable; install axonx-studio to enable it")
            else:
                mount_studio(server, static_dir)
        return server

    @asynccontextmanager
    async def _lifespan(self, app: "Application", _server):
        async with app:
            previous_target = os.environ.get(AXONX_SERVICE_TARGET)
            target = self.local_target
            os.environ[AXONX_SERVICE_TARGET] = target
            self.logger.info(f"Service started: {AXONX_SERVICE_TARGET}={target}")
            if self.token is None:
                self.logger.warning(
                    "The HTTP service is unauthenticated; set service.token before "
                    "exposing it beyond a trusted network",
                )
            readiness = asyncio.create_task(self._notify_ready())
            try:
                yield
            finally:
                try:
                    self.request_shutdown()
                finally:
                    readiness.cancel()
                    try:
                        await asyncio.gather(readiness, return_exceptions=True)
                    finally:
                        if previous_target is None:
                            os.environ.pop(AXONX_SERVICE_TARGET, None)
                        else:
                            os.environ[AXONX_SERVICE_TARGET] = previous_target

    async def _notify_ready(self) -> None:
        callback = self.on_ready
        if self.server is None or callback is None:
            return
        while not self.server.started:
            await asyncio.sleep(0.05)
        await callback()  # pylint: disable=not-callable

    def run_app(self, app: "Application") -> None:
        """Serve the application with Uvicorn until shutdown."""
        import uvicorn

        from .shutdown import (
            ShutdownDeadline,
            ShutdownServer,
        )

        deadline = ShutdownDeadline(app, self.cleanup_timeout)
        self._shutdown_deadline = deadline
        try:
            self.server = ShutdownServer(
                uvicorn.Config(
                    self.build_service(app),
                    host=self.host,
                    port=self.port,
                    timeout_graceful_shutdown=self.shutdown_timeout,
                ),
                self.request_shutdown,
            )
            self.server.run()
        finally:
            deadline.close()
            self._shutdown_deadline = None
        if not self.server.started:
            raise RuntimeError("HTTP service failed to start")

    def request_shutdown(self, *, force: bool = False) -> None:
        """Stop accepting requests after the update response has been delivered."""
        if self.server is not None:
            self.server.should_exit = True
        self.stop_cli_processes(force=force)
        if self._shutdown_deadline is not None:
            self._shutdown_deadline.request(force=force)

    def stop_cli_processes(self, *, force: bool = False) -> None:
        """Signal only process groups created by this service's CLI Job."""
        for pid in tuple(self.cli_processes):
            try:
                os.killpg(pid, signal.SIGKILL if force else signal.SIGTERM)
            except ProcessLookupError:
                pass
