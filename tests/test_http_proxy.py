"""Generic HTTP proxy component and route tests."""

import json

import httpx
import pytest
from pydantic import ValidationError

from axonx import Application
from axonx.components.proxy import BaseProxyComponent, HttpProxyComponent
from axonx.components.service import HttpService
from axonx.enums import ComponentEnum, JobMode
from axonx.schema import ProxyResponse


def test_http_backend_implements_proxy_contract():
    assert issubclass(HttpProxyComponent, BaseProxyComponent)
    assert BaseProxyComponent.component_type is ComponentEnum.PROXY


def test_proxy_response_validates_status_and_is_frozen():
    response = ProxyResponse(status_code=200, content=b"ok")

    assert response.headers == {}
    with pytest.raises(ValidationError):
        response.status_code = 201
    with pytest.raises(ValidationError):
        ProxyResponse(status_code=99, content=b"")


def build_app(handler, *, secret="secret-token", max_request_bytes=1_048_576):
    return Application(
        log_to_file=False,
        components={
            "proxy": {
                "upstream": {
                    "backend": "http",
                    "upstream_base_url": "http://upstream.example/api",
                    "request_secret": secret,
                    "request_secret_json_path": "credentials.secret",
                    "json_overrides": {
                        "credentials.secret": secret,
                        "metadata.origin": "http://upstream.example/api",
                    },
                    "transport": httpx.MockTransport(handler),
                },
            },
        },
        jobs={
            "mirror": {
                "backend": "proxy",
                "component": "upstream",
                "path_prefix": "/mirror",
                "max_request_bytes": max_request_bytes,
            },
        },
    )


async def test_proxy_forwards_request_and_applies_json_overrides():
    captured = {}

    def upstream(request):
        captured["url"] = str(request.url)
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"code": 0, "data": []})

    app = build_app(upstream)
    server = HttpService().build_service(app)
    payload = {
        "credentials": {"secret": "secret-token"},
        "metadata": {"origin": "http://client/mirror"},
    }

    async with app:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=server), base_url="http://test"
        ) as client:
            response = await client.post("/mirror/resource?limit=2", json=payload)

    assert response.status_code == 200
    assert response.json() == {"code": 0, "data": []}
    assert captured["url"] == "http://upstream.example/api/resource?limit=2"
    assert captured["payload"]["credentials"]["secret"] == "secret-token"
    assert captured["payload"]["metadata"]["origin"] == "http://upstream.example/api"


async def test_proxy_rejects_invalid_secret_without_contacting_upstream():
    contacted = False

    def upstream(_request):
        nonlocal contacted
        contacted = True
        return httpx.Response(200)

    app = build_app(upstream)
    server = HttpService().build_service(app)
    async with app:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=server), base_url="http://test"
        ) as client:
            response = await client.post(
                "/mirror/resource",
                json={"credentials": {"secret": "wrong"}},
            )

    assert response.status_code == 401
    assert not contacted


async def test_proxy_preserves_upstream_status_body_and_selected_headers():
    def upstream(_request):
        return httpx.Response(
            429,
            json={"code": -1, "message": "rate limited"},
            headers={"retry-after": "5", "x-internal": "hidden"},
        )

    app = build_app(upstream)
    server = HttpService().build_service(app)
    async with app:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=server), base_url="http://test"
        ) as client:
            response = await client.post(
                "/mirror/resource",
                json={"credentials": {"secret": "secret-token"}},
            )

    assert response.status_code == 429
    assert response.json() == {"code": -1, "message": "rate limited"}
    assert response.headers["retry-after"] == "5"
    assert "x-internal" not in response.headers


async def test_proxy_rejects_oversized_request():
    app = build_app(lambda _request: httpx.Response(200), max_request_bytes=10)
    server = HttpService().build_service(app)
    async with app:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=server), base_url="http://test"
        ) as client:
            response = await client.post("/mirror/resource", content=b"01234567890")

    assert response.status_code == 413


async def test_proxy_route_job_rejects_direct_invocation():
    app = build_app(lambda _request: httpx.Response(200))
    job = app.context.jobs["mirror"]

    assert job.mode is JobMode.HTTP_ROUTE
    assert not job.is_invocable
    assert not job.is_servable
    async with app:
        with pytest.raises(
            ValueError,
            match="does not support direct invocation.*http_route",
        ):
            await app.run_job("mirror")
