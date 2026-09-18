"""HTTP proxy route backed by a generic proxy component."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

import httpx
from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import Response

from ...enums import JobMode
from ..registry import R
from ..proxy import BaseProxyComponent
from .base import BaseJob

if TYPE_CHECKING:
    from fastapi import FastAPI


@R.register("proxy")
class ProxyRouteJob(BaseJob):
    """Mount a configurable reverse-proxy route on the HTTP service."""

    @property
    def mode(self) -> JobMode:
        """Mount an HTTP route instead of accepting direct invocation."""
        return JobMode.HTTP_ROUTE

    def __init__(
        self,
        component: str = "default",
        path_prefix: str = "/proxy",
        methods: Sequence[str] = ("POST",),
        max_request_bytes: int = 1_048_576,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        prefix = path_prefix.rstrip("/")
        if not prefix.startswith("/") or prefix == "":
            raise ValueError("Proxy path_prefix must start with '/'")
        normalized_methods = tuple(dict.fromkeys(method.upper() for method in methods))
        if not normalized_methods or any(not method.isalpha() for method in normalized_methods):
            raise ValueError("Proxy methods must contain valid HTTP method names")
        if max_request_bytes <= 0:
            raise ValueError("Proxy max_request_bytes must be greater than 0")
        self.proxy = self.bind(component, BaseProxyComponent, optional=False)
        self.path_prefix = prefix
        self.methods = normalized_methods
        self.max_request_bytes = max_request_bytes

    async def _read_body(self, request: Request) -> bytes:
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                length = int(content_length)
            except ValueError as exc:
                raise HTTPException(400, "Invalid Content-Length") from exc
            if length < 0:
                raise HTTPException(400, "Invalid Content-Length")
            if length > self.max_request_bytes:
                raise HTTPException(413, "Proxy request is too large")

        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > self.max_request_bytes:
                raise HTTPException(413, "Proxy request is too large")
            body.extend(chunk)
        return bytes(body)

    async def _forward(self, proxy_path: str, request: Request) -> Response:
        body = await self._read_body(request)
        # Request bodies and query values may contain credentials.
        self.logger.info(
            f"Proxy endpoint called: name={self.name} method={request.method} "
            f"path={proxy_path} body_bytes={len(body)}"
        )
        try:
            result = await self.proxy.forward(
                request.method,
                proxy_path,
                query=tuple(request.query_params.multi_items()),
                headers=request.headers,
                content=body,
            )
        except PermissionError as exc:
            raise HTTPException(401, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except httpx.TimeoutException as exc:
            raise HTTPException(504, "Proxy upstream timed out") from exc
        except httpx.HTTPError as exc:
            self.logger.warning(f"Proxy upstream request failed: {exc}")
            raise HTTPException(502, "Proxy upstream request failed") from exc
        return Response(
            content=result.content,
            status_code=result.status_code,
            headers=result.headers,
        )

    def mount_http_routes(self, server: FastAPI) -> None:
        """Add the configured proxy endpoint to a FastAPI application."""
        server.add_api_route(
            f"{self.path_prefix}/{{proxy_path:path}}",
            self._forward,
            methods=list(self.methods),
            include_in_schema=False,
            name=f"{self.name}_forward",
        )
