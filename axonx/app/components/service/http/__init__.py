"""HTTP service implementation and endpoint capabilities.

service: HTTP component configuration and application serving.
app: ASGI application assembly, authentication and shared lifespan.
files: Raw and multipart upload staging.
jobs: Job catalogs, calls, event streams and MCP tools.
proxy: Routes forwarding requests to configured proxy components.
shutdown: Process-level shutdown deadlines and Uvicorn integration.
studio: Optional Studio static assets and frontend routing.
"""

from . import app, files, jobs, proxy, service, shutdown, studio
from .service import HttpService

__all__ = [
    "HttpService",
    "app",
    "files",
    "jobs",
    "proxy",
    "service",
    "shutdown",
    "studio",
]
