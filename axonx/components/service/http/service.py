"""HTTP service component backed by FastAPI and Uvicorn."""

from typing import TYPE_CHECKING

from ....constants import AXONX_DEFAULT_BIND_HOST, AXONX_DEFAULT_PORT
from ....workspace.staging import StagedFiles
from ...registry import provider
from ..base import BaseService

if TYPE_CHECKING:
    from fastapi import FastAPI

    from ....core import Application


@provider("http")
class HttpService(BaseService):
    """Expose ordinary Jobs over JSON and MCP, plus events and file transfer."""

    def __init__(
        self,
        host: str = AXONX_DEFAULT_BIND_HOST,
        port: int = AXONX_DEFAULT_PORT,
        shutdown_timeout: int = 1,
        web_enabled: bool = True,
        web_static_dir: str | None = None,
        token: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        if shutdown_timeout < 0:
            raise ValueError("shutdown_timeout must be non-negative")
        if token is not None and (not isinstance(token, str) or not token):
            raise ValueError("token must be a non-empty string")
        self.host, self.port = host, port
        self.shutdown_timeout = shutdown_timeout
        self.web_enabled = web_enabled
        self.web_static_dir = web_static_dir
        self.token = token
        self.staged_files: StagedFiles | None = None

    def build_service(self, app: "Application") -> "FastAPI":
        """Build the ASGI application without starting a server."""
        from .app import create_http_app

        self.staged_files = StagedFiles(app.workspace_path)
        return create_http_app(app, self)

    def run_app(self, app: "Application") -> None:
        """Serve the application with Uvicorn until shutdown."""
        import uvicorn

        uvicorn.run(
            self.build_service(app),
            host=self.host,
            port=self.port,
            timeout_graceful_shutdown=self.shutdown_timeout,
        )


__all__ = ["HttpService"]
