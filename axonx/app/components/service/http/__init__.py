"""HTTP service implementation and endpoint capabilities.

files: FileRoutes stages raw or multipart uploads and discards staged files.
jobs: JobRoutes shares request envelopes and public Jobs across JSON, SSE, and MCP.
middleware: HTTP protocol authentication and response-completion policy boundaries.
proxy: Expose configured proxy components as transparent HTTP routes.
service: HTTP component, FastAPI/MCP application assembly, lifespan and Uvicorn execution.
shutdown: Process-level shutdown deadline, independent of asyncio and executor drains.
studio: Optional Studio static site mounting.
"""

from . import files, jobs, middleware, proxy, service, shutdown, studio

__all__ = [
    "files",
    "jobs",
    "middleware",
    "proxy",
    "service",
    "shutdown",
    "studio",
]
