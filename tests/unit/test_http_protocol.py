"""Contract tests for the three AxonX HTTP protocol surfaces."""

import asyncio
import hashlib
import socket

import httpx
import pytest
import uvicorn

from axonx.components.client import HttpClient, McpClient
from axonx.components.job import ArtifactEvent, ResultEvent
from axonx.components.service import HttpService
from axonx.core import Application


def _application(tmp_path, **extra):
    config = {
        "workspace_dir": str(tmp_path),
        "enable_logo": False,
        "log_to_console": False,
        "log_to_file": False,
        "jobs": {
            "version": {
                "requires_auth": False,
                "steps": [{"backend": "version_step"}],
            }
        },
    }
    config.update(extra)
    return Application(**config)


@pytest.mark.asyncio
async def test_http_protocol_uses_one_token_for_jobs_events_and_files(tmp_path):
    app = _application(tmp_path / "workspace")
    service = HttpService(token="secret", web_enabled=False)
    server = service.build_service(app)
    transport = httpx.ASGITransport(app=server)

    async with server.router.lifespan_context(server):
        async with httpx.AsyncClient(
            base_url="http://test", transport=transport
        ) as raw:
            assert (await raw.get("/health")).status_code == 401
            assert (await raw.post("/mcp")).status_code == 401
            assert (await raw.get("/docs")).status_code == 200
            assert (await raw.get("/redoc")).status_code == 200
            openapi = await raw.get("/openapi.json")
            assert openapi.status_code == 200
            assert openapi.json()["openapi"]

        async with HttpClient(token="secret", transport=transport) as client:
            assert await client.health() is True
            response = await client.run_job("version")
            assert response.success is True

            events = [event async for event in client.stream_job("version")]
            assert len(events) == 1
            assert isinstance(events[0], ResultEvent)
            assert events[0].success is True

            source = tmp_path / "payload.bin"
            source.write_bytes(b"axonx-http-protocol")
            copied = await client.copy_file(source)
            assert copied.sha256 == hashlib.sha256(source.read_bytes()).hexdigest()
            assert copied.size == source.stat().st_size
            assert (
                tmp_path / "workspace" / copied.path
            ).read_bytes() == source.read_bytes()
            assert await client.discard_file(copied.path) == copied.path
            assert not (tmp_path / "workspace" / copied.path).exists()


@pytest.mark.asyncio
async def test_event_endpoint_stops_at_first_result_and_closes_source(tmp_path):
    closed = False

    async def events():
        nonlocal closed
        try:
            yield ArtifactEvent(path="before")
            yield ResultEvent(answer="done")
            yield ArtifactEvent(path="after")
        finally:
            closed = True

    app = _application(tmp_path / "workspace")
    app.stream_job = lambda _name, **_arguments: events()
    server = HttpService(web_enabled=False).build_service(app)
    transport = httpx.ASGITransport(app=server)
    async with server.router.lifespan_context(server):
        async with HttpClient(transport=transport) as client:
            received = [event async for event in client.stream_job("version")]

    assert [event.kind for event in received] == ["artifact", "result"]
    assert closed is True


@pytest.mark.asyncio
async def test_mcp_client_calls_the_ordinary_response_surface(tmp_path):
    app = _application(tmp_path / "workspace")
    server_app = HttpService(token="secret", web_enabled=False).build_service(app)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(server_app, log_level="error"))
    task = asyncio.create_task(server.serve(sockets=[listener]))
    while not server.started:
        await asyncio.sleep(0.01)
    try:
        async with McpClient(
            host_ip="127.0.0.1", host_port=port, token="secret"
        ) as client:
            assert [job.name for job in await client.list_jobs()] == ["version"]
            response = await client.run_job("version")
            assert response.success is True
    finally:
        server.should_exit = True
        await task


@pytest.mark.asyncio
async def test_jobs_require_auth_by_default_and_can_be_made_public(tmp_path):
    app = _application(
        tmp_path / "workspace",
        jobs={
            "public": {
                "requires_auth": False,
                "steps": [{"backend": "version_step"}],
            },
            "protected": {"steps": [{"backend": "version_step"}]},
        },
    )
    server = HttpService(web_enabled=False).build_service(app)
    transport = httpx.ASGITransport(app=server)
    async with server.router.lifespan_context(server):
        async with httpx.AsyncClient(
            base_url="http://test", transport=transport
        ) as client:
            catalog = (await client.get("/jobs")).json()["answer"]["items"]
            assert [job["name"] for job in catalog] == ["public"]
            assert (await client.post("/jobs/protected", json={})).status_code == 404

    protected_server = HttpService(token="secret", web_enabled=False).build_service(app)
    protected_transport = httpx.ASGITransport(app=protected_server)
    async with protected_server.router.lifespan_context(protected_server):
        async with httpx.AsyncClient(
            base_url="http://test",
            transport=protected_transport,
            headers={"authorization": "Bearer secret"},
        ) as client:
            catalog = (await client.get("/jobs")).json()["answer"]["items"]
            assert [job["name"] for job in catalog] == ["public", "protected"]
