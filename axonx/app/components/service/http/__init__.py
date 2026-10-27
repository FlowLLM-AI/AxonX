"""HTTP service implementation and endpoint capabilities.

app: ASGI application factory for the HTTP service.
files: Stage raw binary or multipart file uploads through the same HTTP endpoint.
jobs: Expose Jobs as JSON responses, event streams, and MCP tools.
middleware: HTTP protocol authentication and response-completion policy boundaries.
models: HTTP request envelopes for the public Job surface.
proxy: Expose configured proxy components as transparent HTTP routes.
service: HTTP service component backed by FastAPI and Uvicorn.
shutdown: Process-level shutdown deadline, independent of asyncio and executor drains.
studio: Optional Studio static site mounting.
"""
