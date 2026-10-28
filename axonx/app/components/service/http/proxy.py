"""Expose configured proxy components as transparent HTTP routes."""

from fastapi import APIRouter, HTTPException, Request
from starlette.responses import StreamingResponse

from ...proxy.base import BaseProxyComponent, ProxyError

_PROXY_METHODS = ("DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT")


def create_proxy_router(app) -> APIRouter:
    """Route ``/proxy/{name}`` to the correspondingly named component."""
    router = APIRouter(prefix="/proxy", include_in_schema=False)
    proxies = app.context.components.get(BaseProxyComponent.component_type, {})

    async def forward(name: str, request: Request) -> StreamingResponse:
        proxy = proxies.get(name)
        if proxy is None:
            raise HTTPException(404, "Unknown proxy")

        path = request.path_params.get("path", "")
        proxy.logger.info(f"Proxy request method={request.method} path={path or '/'}")
        try:
            result = await proxy.forward(
                request.method,
                path,
                query=tuple(request.query_params.multi_items()),
                headers=tuple(request.headers.items()),
                content=request.stream(),
            )
        except ProxyError as exc:
            raise HTTPException(exc.status_code, str(exc)) from exc

        response = StreamingResponse(result.iter_bytes(), status_code=result.status_code)
        for key, value in result.headers:
            response.headers.append(key, value)
        return response

    for route in ("/{name}", "/{name}/{path:path}"):
        router.add_api_route(route, forward, methods=list(_PROXY_METHODS))
    return router
