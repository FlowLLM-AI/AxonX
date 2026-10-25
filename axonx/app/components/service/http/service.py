"""HTTP service component backed by FastAPI and Uvicorn."""

import math
import os
import signal
from pathlib import Path
from typing import TYPE_CHECKING

from ..base import BaseService
from .....common.constants import AXONX_DEFAULT_BIND_HOST, AXONX_DEFAULT_PORT
from .....common.registry import provider

if TYPE_CHECKING:
    from fastapi import FastAPI

    from ....core.application import Application


@provider("http")
class HttpService(BaseService):
    """Expose ordinary Jobs over JSON and MCP, plus events and file transfer."""

    def __init__(
        self,
        host: str = AXONX_DEFAULT_BIND_HOST,
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
        self.host, self.port = host, port
        self.shutdown_timeout = shutdown_timeout
        self.cleanup_timeout = cleanup_timeout
        self._shutdown_deadline = None
        self.web_enabled = web_enabled
        self.token = token
        self.server = None
        self.startup_directory = Path.cwd().resolve()
        self.cli_processes: set[int] = set()
        self.cli_callbacks: dict[str, list | None] = {}

    def build_service(self, app: "Application") -> "FastAPI":
        """Build the ASGI application without starting a server."""
        from .app import create_http_app

        return create_http_app(app, self)

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
