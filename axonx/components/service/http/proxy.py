"""Expose configured proxy components as transparent HTTP routes."""

from fastapi import APIRouter, HTTPException, Request
from starlette.responses import Response

from ....components.proxy import ProxyError
from ....constants import PROTOCOL_ROUTE_PROXY
from ....enums import ComponentEnum

_PROXY_METHODS = ("DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT")


def create_proxy_router(app) -> APIRouter:
    """Route ``/proxy/{name}`` to the correspondingly named component."""
    router = APIRouter(prefix=PROTOCOL_ROUTE_PROXY, include_in_schema=False)
    proxies = app.context.components.get(ComponentEnum.PROXY, {})

    async def dispatch(name: str, path: str, request: Request) -> Response:
        proxy = proxies.get(name)
        if proxy is None:
            raise HTTPException(404, "Unknown proxy")

        body = await request.body()
        proxy.logger.info(
            f"Proxy request method={request.method} path={path or '/'} "
            f"body_bytes={len(body)}"
        )
        try:
            result = await proxy.forward(
                request.method,
                path,
                query=tuple(request.query_params.multi_items()),
                headers=tuple(request.headers.items()),
                content=body,
            )
        except ProxyError as exc:
            raise HTTPException(exc.status_code, str(exc)) from exc

        response = Response(content=result.content, status_code=result.status_code)
        for key, value in result.headers:
            response.headers.append(key, value)
        return response

    async def forward_root(name: str, request: Request) -> Response:
        return await dispatch(name, "", request)

    async def forward_path(name: str, path: str, request: Request) -> Response:
        return await dispatch(name, path, request)

    router.add_api_route("/{name}", forward_root, methods=list(_PROXY_METHODS))
    router.add_api_route(
        "/{name}/{path:path}",
        forward_path,
        methods=list(_PROXY_METHODS),
    )
    return router
