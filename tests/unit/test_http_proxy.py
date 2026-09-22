"""Contract tests for transparent named HTTP proxies."""

import httpx
import pytest

from axonx.components.proxy import HttpProxyComponent
from axonx.components.service import HttpService
from axonx.config import ConfigResolver
from axonx.core import Application
from axonx.enums import ComponentEnum


@pytest.mark.asyncio
async def test_named_proxy_forwards_request_and_upstream_response(tmp_path):
    received: dict[str, object] = {}

    async def upstream(request: httpx.Request) -> httpx.Response:
        received.update(
            method=request.method,
            url=str(request.url),
            headers=dict(request.headers),
            content=await request.aread(),
        )
        return httpx.Response(
            201,
            content=b'{"ok":true}',
            headers=[
                ("content-type", "application/json"),
                ("x-upstream", "yes"),
                ("connection", "x-hop"),
                ("x-hop", "discarded"),
                ("set-cookie", "first=1"),
                ("set-cookie", "second=2"),
            ],
        )

    app = Application(
        workspace_dir=str(tmp_path),
        enable_logo=False,
        log_to_console=False,
        log_to_file=False,
        components={
            "proxy": {
                "tushare": {
                    "backend": "http",
                    "upstream_base_url": "http://upstream/dataapi",
                }
            }
        },
    )
    proxy = app.context.components[ComponentEnum.PROXY]["tushare"]
    proxy._transport = httpx.MockTransport(upstream)

    server = HttpService(token="service-secret", web_enabled=False).build_service(app)
    transport = httpx.ASGITransport(app=server)
    payload = b'{"api_name":"daily","token":"caller-token"}'

    async with (
        server.router.lifespan_context(server),
        httpx.AsyncClient(base_url="http://test", transport=transport) as client,
    ):
        response = await client.post(
            "/proxy/tushare/daily?tag=a&tag=b",
            content=payload,
            headers={
                "authorization": "Bearer upstream-token",
                "content-type": "application/json",
                "x-custom": "preserved",
                "connection": "x-local-hop",
                "x-local-hop": "discarded",
            },
        )
        missing = await client.post("/proxy/missing/daily", content=payload)

    assert response.status_code == 201
    assert response.content == b'{"ok":true}'
    assert response.headers["x-upstream"] == "yes"
    assert response.headers.get_list("set-cookie") == ["first=1", "second=2"]
    assert "x-hop" not in response.headers
    assert missing.status_code == 404
    assert received["method"] == "POST"
    assert received["url"] == "http://upstream/dataapi/daily?tag=a&tag=b"
    assert received["content"] == payload
    headers = received["headers"]
    assert isinstance(headers, dict)
    assert {
        name: headers[name]
        for name in ("authorization", "content-type", "x-custom", "content-length")
    } == {
        "authorization": "Bearer upstream-token",
        "content-type": "application/json",
        "x-custom": "preserved",
        "content-length": str(len(payload)),
    }
    assert "x-local-hop" not in headers


@pytest.mark.asyncio
async def test_proxy_does_not_prebuffer_request_or_response():
    request_started = False
    response_started = False
    response_closed = False
    received_request: httpx.Request | None = None

    async def request_body():
        nonlocal request_started
        request_started = True
        yield b"request"

    class ResponseBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            nonlocal response_started
            response_started = True
            yield b"response"

        async def aclose(self):
            nonlocal response_closed
            response_closed = True

    class Transport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            nonlocal received_request
            received_request = request
            return httpx.Response(200, stream=ResponseBody(), request=request)

    proxy = HttpProxyComponent(
        upstream_base_url="http://upstream",
        transport=Transport(),
    )
    async with proxy:
        result = await proxy.forward("POST", "stream", content=request_body())

        assert request_started is False
        assert response_started is False
        assert received_request is not None
        assert await received_request.aread() == b"request"
        assert b"".join([chunk async for chunk in result.iter_bytes()]) == b"response"
        assert response_closed is True


def test_default_config_does_not_enable_optional_remote_services(monkeypatch):
    monkeypatch.delenv("AXONX_REMOTE_HOST_IP", raising=False)
    config = ConfigResolver().load("default")

    assert config["remote_nodes"] == []
    assert "proxy" not in config["components"]
