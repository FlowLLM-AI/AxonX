"""Check the upstream resource boundary when a downstream consumer is cancelled."""

import asyncio
import gzip

import httpx
import pytest

from axonx.app.components.proxy.base import ProxyResponse
from axonx.app.components.proxy.http import HttpProxyComponent


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
