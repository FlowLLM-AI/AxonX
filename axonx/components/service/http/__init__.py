"""HTTP service component and compatibility entry point."""

from typing import TYPE_CHECKING, Any

from ....constants import AXONX_DEFAULT_BIND_HOST, AXONX_DEFAULT_PORT
from ...registry import R
from ..base import BaseService

if TYPE_CHECKING:
    from fastapi import FastAPI
    from fastmcp import FastMCP

    from ....core import Application


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
        self.mcp_server: "FastMCP | None" = None

    def build_service(self, app: "Application") -> "FastAPI":
        """Build the ASGI application without starting a server."""
        from .app import create_http_app

        return create_http_app(app, self)

    def _resolve_web_static_dir(self):
        """Retain the service's static directory lookup entry point."""
        from .static import resolve_web_static_dir

        return resolve_web_static_dir(self.web_static_dir)

    def run_app(self, app):
        """Serve the application with Uvicorn until shutdown."""
        import uvicorn

        uvicorn.run(
            self.build_service(app),
            host=self.host,
            port=self.port,
            timeout_graceful_shutdown=self.shutdown_timeout,
        )
