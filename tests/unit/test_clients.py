"""Exercise the public service clients, protocol boundaries and owned resources."""

import asyncio
from contextlib import aclosing
from io import BytesIO
from pathlib import Path
from threading import Event
from unittest.mock import AsyncMock

import httpx
import pytest
from fastmcp import Client as SDKClient
from fastmcp import FastMCP

from axonx.app.components.service.http.jobs import JobRoutes
from axonx.app.core.application import Application
from axonx.client.base import RemoteConnectionError, RemoteServiceError
from axonx.client.config import (
    AXONX_DEFAULT_TARGET,
    ConnectionOptions,
    normalize_target,
)
from axonx.client.events import ResultEvent
from axonx.client.http import HttpClient, run_remote_job, stream_remote_job
from axonx.client.mcp import McpClient
from axonx.client.models import JobResponse
from axonx.task.models.events import LogEvent


async def test_http_client_round_trip_with_the_application(tmp_path):
    app = Application(
        workspace_dir=str(tmp_path / "workspace"),
        log_to_console=False,
        log_to_file=False,
        jobs={"version": {"steps": [{"backend": "version_step"}]}},
        service={"backend": "http", "token": "test-token", "web_enabled": False},
    )
    source = tmp_path / "source.txt"
    source.write_bytes(b"data" * 300_000)
    async with app:
        transport = httpx.ASGITransport(app=app.context.service.build_service(app))
        async with HttpClient(target="service:1024", token="test-token", transport=transport) as remote:
            assert await remote.health()
            assert [job.name for job in await remote.list_jobs()] == ["version"]
            response = await remote.run_job("version")
            assert response.success
            events = [event async for event in remote.stream_job("version")]
            assert isinstance(events[-1], ResultEvent)
            assert events[-1].response() == response
            copied = await remote.copy_file(source)
            assert copied.size == source.stat().st_size
            assert source.read_bytes() == (app.workspace.root / copied.path).read_bytes()
            assert await remote.discard_file(copied.path) == copied.path
            assert not (app.workspace.root / copied.path).exists()
        async with HttpClient(target="service:1024", token="wrong", transport=transport) as remote:
            assert not await remote.health()
            with pytest.raises(RemoteServiceError) as error:
                await remote.run_job("version")
            assert error.value.status_code == 401


async def test_short_lived_job_preserves_authentication_request_identity_and_business_failure(
    monkeypatch,
):
    monkeypatch.setenv("AXONX_CLI_REQUEST_ID", "request-id")

    def respond(request):
        assert request.headers["authorization"] == "Bearer test-token"
        assert request.headers["x-axonx-cli-request"] == "request-id"
        assert request.url.path == "/jobs/example"
        assert request.content == b'{"arguments":{"value":3}}'
        return httpx.Response(
            200,
            json={
                "answer": "rejected",
                "success": False,
                "metadata": {"reason": "business"},
            },
        )

    response = await run_remote_job(
        "example",
        {"value": 3},
        target="service:1024",
        token="test-token",
        transport=httpx.MockTransport(respond),
    )
    assert response == JobResponse(answer="rejected", success=False, metadata={"reason": "business"})


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {"answer": "incomplete"},
        {"answer": "bad type", "success": "true", "metadata": {}},
    ],
)
async def test_http_client_rejects_invalid_remote_envelopes(payload):
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    with pytest.raises(RemoteServiceError, match="invalid response envelope"):
        await run_remote_job("example", {}, target="service:1024", transport=transport)


@pytest.mark.parametrize("error_type", [httpx.ConnectError, httpx.ReadTimeout])
async def test_connection_failures_are_distinct_from_protocol_errors(error_type):
    def fail(request):
        raise error_type("unavailable", request=request)

    with pytest.raises(RemoteConnectionError):
        await run_remote_job("get_config", {}, target="service:1024", transport=httpx.MockTransport(fail))


@pytest.mark.parametrize(
    ("content_type", "body", "message"),
    [
        ("application/json", b"{}", "non-event stream"),
        ("text/event-stream-invalid", b"{}", "non-event stream"),
        (
            "text/event-stream",
            b'data: {"kind":"log","content":"hello"}\n\n',
            "without a terminal result",
        ),
        ("text/event-stream", b'data: {"kind":"unknown"}\n\n', "invalid stream event"),
        (
            "text/event-stream",
            b'data: {"kind":"result","answer":"incomplete"}\n\n',
            "invalid response envelope",
        ),
    ],
)
async def test_stream_protocol_errors_are_reported(content_type, body, message):
    transport = httpx.MockTransport(lambda _: httpx.Response(200, headers={"content-type": content_type}, content=body))
    with pytest.raises(RemoteServiceError, match=message):
        async with aclosing(stream_remote_job("example", {}, target="service:1024", transport=transport)) as events:
            async for _ in events:
                pass


async def test_stopping_a_short_lived_stream_closes_its_response_and_transport():
    closed = []

    class EventStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'data: {"kind":"log","content":"hello"}\n\n'
            yield b'data: {"kind":"result","answer":"done","success":true,"metadata":{}}\n\n'

        async def aclose(self):
            closed.append("response")

    class Transport(httpx.MockTransport):
        async def aclose(self):
            closed.append("transport")

    transport = Transport(
        lambda _: httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=EventStream())
    )
    async with aclosing(stream_remote_job("example", {}, target="service:1024", transport=transport)) as events:
        assert isinstance(await anext(events), LogEvent)
    assert closed == ["response", "transport"]


async def test_repeated_cancellation_waits_for_owned_connection_cleanup():
    closing, release, closed = asyncio.Event(), asyncio.Event(), asyncio.Event()

    class Transport(httpx.MockTransport):
        async def aclose(self):
            closing.set()
            await release.wait()
            closed.set()

    remote = HttpClient(target="service:1024", transport=Transport(lambda _: httpx.Response(200)))
    await asyncio.gather(remote.start(), remote.start())
    cleanup = asyncio.create_task(remote.close())
    await closing.wait()
    try:
        for _ in range(2):
            cleanup.cancel()
            await asyncio.sleep(0)
            assert not cleanup.done()
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await cleanup
    assert closed.is_set()
    assert not remote.is_started


async def test_cancelled_upload_finishes_reading_before_closing_the_file(tmp_path, monkeypatch):
    source = tmp_path / "source.txt"
    source.write_bytes(b"abc")
    reading, release = asyncio.Event(), Event()
    loop = asyncio.get_running_loop()

    class Reader(BytesIO):
        def read(self, size):
            loop.call_soon_threadsafe(reading.set)
            if not release.wait(timeout=5):
                raise TimeoutError("Test did not release the file read")
            return super().read(size)

    reader = Reader(b"abc")
    original_open = Path.open

    def open_file(path, *args, **kwargs):
        return reader if path == source else original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", open_file)
    transport = httpx.MockTransport(lambda _: httpx.Response(200))
    async with HttpClient(target="service:1024", transport=transport) as remote:
        transfer = asyncio.create_task(remote.copy_file(source))
        try:
            await asyncio.wait_for(reading.wait(), timeout=3)
            for _ in range(2):
                transfer.cancel()
                await asyncio.sleep(0)
                assert not transfer.done()
                assert not reader.closed
        finally:
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(transfer, timeout=3)
    assert reader.closed


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        (" SERVICE:1024/ ", "http://service:1024"),
        ("https://service:443", "https://service:443"),
        ("[0:0:0:0:0:0:0:1]:1024", "http://[::1]:1024"),
    ],
)
def test_connection_options_share_canonical_addresses(target, expected):
    assert normalize_target(target) == expected
    assert ConnectionOptions(target=target).target == expected


@pytest.mark.parametrize(
    "target",
    [
        "",
        "service",
        "service:0",
        "service:65536",
        "ftp://service:1024",
        "http://user:token@service:1024",
        "service:1024/jobs",
        "service:1024?token=value",
    ],
)
def test_connection_options_reject_invalid_service_addresses(target):
    with pytest.raises(ValueError):
        ConnectionOptions(target=target)


def test_clients_resolve_explicit_discovered_and_default_addresses(monkeypatch):
    monkeypatch.delenv("AXONX_SERVICE_TARGET", raising=False)
    assert HttpClient().target == AXONX_DEFAULT_TARGET
    monkeypatch.setenv("AXONX_SERVICE_TARGET", "discovered:2048")
    assert HttpClient().target == "http://discovered:2048"
    assert McpClient(target="explicit:4096").target == "http://explicit:4096"
    monkeypatch.setenv("AXONX_SERVICE_TARGET", "invalid")
    with pytest.raises(ValueError):
        HttpClient()
    assert HttpClient(target="explicit:4096").target == "http://explicit:4096"


@pytest.mark.parametrize(
    ("operation", "answer", "message"),
    [
        ("catalog", {"items": [{"name": "missing schemas"}]}, "JobCatalog payload"),
        ("upload", {"path": "tmp/file", "size": 3}, "StagedFile payload"),
        (
            "upload",
            {"path": "tmp/file", "size": "3", "location": "/workspace/tmp/file"},
            "StagedFile payload",
        ),
    ],
)
async def test_http_client_validates_typed_payloads(tmp_path, operation, answer, message):
    source = tmp_path / "source.txt"
    source.write_text("abc")
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, json={"answer": answer, "success": True, "metadata": {}})
    )
    async with HttpClient(target="service:1024", transport=transport) as remote:
        with pytest.raises(RemoteServiceError, match=message):
            if operation == "catalog":
                await remote.list_jobs()
            else:
                await remote.copy_file(source)


async def test_stream_preserves_failed_terminal_result_and_ignores_later_frames():
    body = (
        b'data: {"kind":"result","answer":"rejected","success":false,"metadata":{"reason":"business"}}\n\n'
        b'data: {"kind":"unknown"}\n\n'
    )
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            200,
            headers={"content-type": "Text/Event-Stream; charset=utf-8"},
            content=body,
        )
    )
    async with aclosing(stream_remote_job("example", {}, target="service:1024", transport=transport)) as events:
        results = [event async for event in events]
    assert results == [ResultEvent(answer="rejected", success=False, metadata={"reason": "business"})]


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {"answer": "incomplete"},
        {"answer": "bad type", "success": "true", "metadata": {}},
    ],
)
async def test_mcp_client_rejects_invalid_remote_envelopes_and_closes_its_connection(monkeypatch, payload):
    sdk = AsyncMock()
    sdk.__aenter__.return_value = sdk
    sdk.call_tool.return_value.structured_content = payload
    monkeypatch.setattr("fastmcp.Client", lambda *args, **kwargs: sdk)
    with pytest.raises(RemoteServiceError, match="invalid response envelope"):
        async with McpClient(target="service:1024") as remote:
            await remote.run_job("example")
    sdk.__aexit__.assert_awaited_once()


async def test_mcp_health_reports_transport_failure(monkeypatch):
    sdk = AsyncMock()
    sdk.__aenter__.return_value = sdk
    sdk.list_tools.return_value = []
    monkeypatch.setattr("fastmcp.Client", lambda *args, **kwargs: sdk)
    async with McpClient(target="service:1024") as remote:
        assert await remote.health()
        sdk.list_tools.side_effect = OSError("offline")
        assert not await remote.health()


def test_result_conversion_preserves_model_answers_and_response_fields():
    answer = ConnectionOptions(target="service:1024")
    response = JobResponse(answer=answer, success=False, metadata={"reason": "business"})
    event = ResultEvent.from_response(response)
    restored = event.response()
    assert restored == response
    assert restored.answer is answer
    assert restored.model_fields_set == {"answer", "success", "metadata"}


async def test_mcp_client_calls_application_jobs_with_the_latest_sdk(tmp_path, monkeypatch):
    app = Application(
        workspace_dir=str(tmp_path),
        log_to_console=False,
        log_to_file=False,
        jobs={"get_config": {"steps": [{"backend": "get_config_step"}]}},
    )
    server = JobRoutes(app, authenticated=True).create_mcp_server()
    monkeypatch.setattr(
        "fastmcp.Client",
        lambda url, *, timeout, auth: SDKClient(server, timeout=timeout),
    )
    async with app, McpClient(target="service:1024") as remote:
        assert await remote.health()
        assert [job.name for job in await remote.list_jobs()] == ["get_config"]
        response = await remote.run_job("get_config")
        assert response.success
        assert response.answer["workspace_dir"] == str(tmp_path)


@pytest.mark.filterwarnings("error::DeprecationWarning")
async def test_mcp_client_uses_the_current_sdk_contract(monkeypatch):
    server = FastMCP("client-test")

    @server.tool
    async def echo(value: int) -> JobResponse:
        return JobResponse(answer=value)

    def connect(url, *, timeout, auth):
        assert url == "http://service:1024/mcp"
        return SDKClient(server, timeout=timeout)

    monkeypatch.setattr("fastmcp.Client", connect)
    async with McpClient(target="service:1024") as remote:
        assert await remote.health()
        jobs = await remote.list_jobs()
        assert [job.name for job in jobs] == ["echo"]
        assert jobs[0].input_schema["properties"]["value"]["type"] == "integer"
        assert "success" in jobs[0].output_schema["properties"]
        assert await remote.run_job("echo", {"value": 3}) == JobResponse(answer=3)
    assert not remote.is_started
