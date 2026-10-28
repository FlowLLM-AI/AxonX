"""Exercise HTTP forwarding, request isolation, and streaming resource ownership."""

import asyncio
import gzip
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from axonx.app.components.proxy.base import ProxyError, ProxyResponse
from axonx.app.components.proxy.http import HttpProxyComponent
from axonx.app.components.service.http.proxy import create_proxy_router


@pytest.mark.parametrize(
    "path",
    ["https://other.test/path", "//other.test/path", "/absolute", "../escape", "nested/%2e%2e/escape", "bad\npath"],
)
async def test_proxy_rejects_paths_that_leave_its_upstream_prefix(path):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200)

    async with HttpProxyComponent(
        upstream_base_url="https://example.test/base", transport=httpx.MockTransport(respond)
    ) as proxy:
        with pytest.raises(ProxyError, match="Invalid proxy request path") as error:
            await proxy.forward("GET", path)
        assert error.value.status_code == 422
    assert not requests


@pytest.mark.parametrize("path", ["folder/a?b#c", "folder/%ab é"])
async def test_proxy_preserves_special_characters_in_the_routed_path(path):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, content=b"ok")

    async with HttpProxyComponent(
        upstream_base_url="https://example.test/base", transport=httpx.MockTransport(respond)
    ) as proxy:
        response = await proxy.forward("GET", path, query=(("x", "1"),))
        assert b"".join([chunk async for chunk in response.iter_bytes()]) == b"ok"
    assert requests[0].url.path == f"/base/{path}"
    assert str(requests[0].url.params) == "x=1"
    assert requests[0].url.fragment == ""


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf")])
def test_proxy_rejects_nonfinite_or_nonpositive_timeouts(timeout):
    with pytest.raises(ValueError, match="timeout must be finite"):
        HttpProxyComponent(upstream_base_url="https://example.test", timeout=timeout)


@pytest.mark.parametrize("url", ["", " ", "example.test", "ftp://example.test", "https://", "https://example.test:bad"])
def test_proxy_rejects_invalid_upstream_configuration(url):
    with pytest.raises(ValueError, match="upstream_base_url"):
        HttpProxyComponent(upstream_base_url=url)


@pytest.mark.parametrize("suffix", ["?query=1", "#fragment", "?", "#"])
def test_proxy_base_url_cannot_contain_a_query_or_fragment(suffix):
    with pytest.raises(ValueError, match="cannot contain a query or fragment"):
        HttpProxyComponent(upstream_base_url=f"https://example.test/base{suffix}")


@pytest.mark.asyncio
async def test_proxy_preserves_repeated_headers_and_strips_connection_owned_fields():
    requests = []
    payload = gzip.compress(b"decoded body")

    def respond(request):
        requests.append(request)
        return httpx.Response(
            200,
            content=payload,
            headers=[
                ("Content-Encoding", "gzip"),
                ("Content-Length", str(len(payload))),
                ("Connection", "X-Remove"),
                ("X-Remove", "private"),
                ("Set-Cookie", "one=1"),
                ("Set-Cookie", "two=2"),
            ],
        )

    proxy = HttpProxyComponent(upstream_base_url="https://example.test/base", transport=httpx.MockTransport(respond))
    async with proxy:
        response = await proxy.forward(
            "GET",
            "resource",
            query=(("x", "1"), ("x", "2")),
            headers=(("Connection", "X-Private"), ("X-Private", "secret"), ("X-Public", "kept")),
        )
        assert b"".join([chunk async for chunk in response.iter_bytes()]) == b"decoded body"
    assert requests[0].url.path == "/base/resource"
    assert requests[0].url.params.get_list("x") == ["1", "2"]
    assert "X-Private" not in requests[0].headers
    assert requests[0].headers["X-Public"] == "kept"
    assert not {key.lower() for key, _ in response.headers} & {"content-encoding", "content-length", "x-remove"}
    assert [value for key, value in response.headers if key.lower() == "set-cookie"] == ["one=1", "two=2"]


async def test_proxy_isolates_cookies_and_forwards_only_supplied_end_to_end_headers():
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, headers={"Set-Cookie": "session=first-user; Path=/"}, content=b"ok")

    async with HttpProxyComponent(
        upstream_base_url="https://example.test/base", transport=httpx.MockTransport(respond)
    ) as proxy:
        for headers in ((), (("Cookie", "session=second-user"),), ()):
            response = await proxy.forward("GET", "resource", headers=headers)
            assert b"".join([chunk async for chunk in response.iter_bytes()]) == b"ok"

    assert [request.headers.get("cookie") for request in requests] == [None, "session=second-user", None]
    for request in requests:
        assert not {"accept", "accept-encoding", "user-agent"} & request.headers.keys()


async def test_proxy_forwards_streaming_body_method_repeated_headers_and_timeout():
    requests = []

    async def body():
        yield b"first"
        yield b"second"

    def respond(request):
        requests.append(request)
        return httpx.Response(201, content=b"created")

    async with HttpProxyComponent(
        upstream_base_url="https://example.test/base/", timeout=12, transport=httpx.MockTransport(respond)
    ) as proxy:
        response = await proxy.forward(
            "PATCH",
            "",
            headers=(("Host", "downstream.test"), ("X-Tag", "one"), ("X-Tag", "two")),
            content=body(),
        )
        assert response.status_code == 201
        assert b"".join([chunk async for chunk in response.iter_bytes()]) == b"created"

    request = requests[0]
    assert request.method == "PATCH"
    assert str(request.url) == "https://example.test/base/"
    assert request.headers["host"] == "example.test"
    assert request.headers.get_list("x-tag") == ["one", "two"]
    assert request.content == b"firstsecond"
    assert set(request.extensions["timeout"].values()) == {12}


@pytest.mark.parametrize(
    ("upstream_error", "status"),
    [(httpx.ConnectError, 502), (httpx.ConnectTimeout, 504), (httpx.ReadTimeout, 504)],
)
async def test_proxy_routes_report_forwarding_errors_and_unknown_components(upstream_error, status):
    def respond(request):
        raise upstream_error("upstream unavailable", request=request)

    proxy = HttpProxyComponent(upstream_base_url="https://example.test/base", transport=httpx.MockTransport(respond))
    application = SimpleNamespace(context=SimpleNamespace(components={"proxy": {"test": proxy}}))
    server = FastAPI()
    server.include_router(create_proxy_router(application))

    async with (
        proxy,
        httpx.AsyncClient(transport=httpx.ASGITransport(app=server), base_url="http://service.test") as client,
    ):
        for path in ("/proxy/test", "/proxy/test/resource"):
            response = await client.get(path)
            assert response.status_code == status
            assert "Proxy upstream" in response.json()["detail"]
        assert (await client.get("/proxy/unknown")).status_code == 404
        assert (await client.get("/proxy/test/https://other.test/path")).status_code == 422


async def test_proxy_routes_preserve_streams_and_repeated_headers():
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(202, content=b"accepted", headers=[("Set-Cookie", "one=1"), ("Set-Cookie", "two=2")])

    proxy = HttpProxyComponent(upstream_base_url="https://example.test/base", transport=httpx.MockTransport(respond))
    application = SimpleNamespace(context=SimpleNamespace(components={"proxy": {"test": proxy}}))
    server = FastAPI()
    server.include_router(create_proxy_router(application))

    async with (
        proxy,
        httpx.AsyncClient(transport=httpx.ASGITransport(app=server), base_url="http://service.test") as client,
    ):
        response = await client.post(
            "/proxy/test/resource?x=1&x=2",
            content=b"payload",
            headers=[("X-Tag", "one"), ("X-Tag", "two")],
        )
        root_response = await client.get("/proxy/test?path=other")

    assert response.status_code == 202
    assert response.content == b"accepted"
    assert response.headers.get_list("set-cookie") == ["one=1", "two=2"]
    assert requests[0].content == b"payload"
    assert requests[0].headers.get_list("x-tag") == ["one", "two"]
    assert requests[0].url.params.get_list("x") == ["1", "2"]
    assert root_response.status_code == 202
    assert requests[1].url.path == "/base/"
    assert requests[1].url.params["path"] == "other"


async def test_proxy_response_stays_streaming_and_closes_on_read_failure():
    class FailingStream(httpx.AsyncByteStream):
        def __init__(self):
            self.closed = False
            self.read = False

        async def __aiter__(self):
            self.read = True
            yield b"first"
            raise httpx.ReadError("stream interrupted")

        async def aclose(self):
            self.closed = True

    stream = FailingStream()
    async with HttpProxyComponent(
        upstream_base_url="https://example.test",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=stream)),
    ) as proxy:
        response = await proxy.forward("GET", "resource")
        assert not stream.read
        content = response.iter_bytes()
        assert await anext(content) == b"first"
        with pytest.raises(httpx.ReadError, match="stream interrupted"):
            await anext(content)
        assert stream.closed


@pytest.mark.asyncio
async def test_repeated_cancellation_waits_for_upstream_close():
    reading, closing, release, closed = (asyncio.Event() for _ in range(4))

    async def body():
        reading.set()
        await asyncio.Event().wait()
        yield b""

    async def close():
        closing.set()
        await release.wait()
        closed.set()

    async def consume():
        response = ProxyResponse(200, body(), close=close)
        return [chunk async for chunk in response.iter_bytes()]

    task = asyncio.create_task(consume())
    try:
        await asyncio.wait_for(reading.wait(), 2)
        task.cancel()
        await asyncio.wait_for(closing.wait(), 2)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 2)
        assert closed.is_set()
    finally:
        release.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
