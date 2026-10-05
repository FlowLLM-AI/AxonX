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
            },
        },
    }
    config.update(extra)
    return Application(**config)


@pytest.mark.asyncio
async def test_http_protocol_uses_one_token_for_jobs_events_and_files(tmp_path):
    """Authenticate all protocol transports with the same service token."""
    app = _application(tmp_path / "workspace")
    service = HttpService(token="secret", web_enabled=False)
    server = service.build_service(app)
    transport = httpx.ASGITransport(app=server)

    async with server.router.lifespan_context(server):
        async with httpx.AsyncClient(base_url="http://test", transport=transport) as raw:
            assert (await raw.get("/health")).status_code == 401
            assert (await raw.post("/mcp")).status_code == 401
            assert (await raw.post("/files", files={"file": ("script.py", b"print(1)")})).status_code == 401
            assert (await raw.get("/docs")).status_code == 200
            assert (await raw.get("/redoc")).status_code == 200
            openapi = await raw.get("/openapi.json")
            assert openapi.status_code == 200
            assert openapi.json()["openapi"]

            multipart = await raw.post(
                "/files",
                files={"file": ("script.py", b"print(1)")},
                headers={"authorization": "Bearer secret"},
            )
            assert multipart.status_code == 200
            assert multipart.json()["success"] is True
            await raw.delete(
                "/files",
                params={"path": multipart.json()["answer"]["path"]},
                headers={"authorization": "Bearer secret"},
            )

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
            assert (tmp_path / "workspace" / copied.path).read_bytes() == source.read_bytes()
            assert await client.discard_file(copied.path) == copied.path
            assert not (tmp_path / "workspace" / copied.path).exists()


@pytest.mark.asyncio
async def test_event_endpoint_stops_at_first_result_and_closes_source(tmp_path):
    """Close the event source as soon as its terminal result is delivered."""
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
    """Expose the same catalog and Job response through MCP."""
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
        async with McpClient(target=f"127.0.0.1:{port}", token="secret") as client:
            assert [job.name for job in await client.list_jobs()] == ["version"]
            response = await client.run_job("version")
            assert response.success is True
    finally:
        server.should_exit = True
        await task


@pytest.mark.asyncio
async def test_jobs_require_auth_by_default_and_can_be_made_public(tmp_path):
    """Hide protected Jobs unless service authentication is configured."""
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
        async with httpx.AsyncClient(base_url="http://test", transport=transport) as client:
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


@pytest.mark.asyncio
async def test_local_backend_forwards_jobs_catalog_and_events_with_target_token(tmp_path, monkeypatch):
    """Forward configured targets using their credentials and preserve failures."""
    remote = _application(
        tmp_path / "remote",
        jobs={"remote_only": {"steps": [{"backend": "version_step"}]}},
    )
    remote_server = HttpService(token="target-secret", web_enabled=False).build_service(remote)
    remote_transport = httpx.ASGITransport(app=remote_server)

    def remote_client(**options):
        return HttpClient(transport=remote_transport, **options)

    monkeypatch.setattr("axonx.components.client.remote.HttpClient", remote_client)
    monkeypatch.setattr("axonx.components.service.http.jobs.HttpClient", remote_client)
    local = _application(
        tmp_path / "local",
        targets=[
            {"address": "remote.test:1024", "token": "target-secret"},
            {"address": "remote.test:1025", "token": "wrong-secret"},
        ],
    )
    server = HttpService(token="local-secret", web_enabled=False).build_service(local)
    async with remote_server.router.lifespan_context(remote_server), server.router.lifespan_context(server):
        async with httpx.AsyncClient(base_url="http://local", transport=httpx.ASGITransport(app=server)) as client:
            invocation = {"target": "remote.test:1024", "arguments": {}}
            assert (await client.post("/jobs/remote_only", json=invocation)).status_code == 401
            client.headers["Authorization"] = "Bearer local-secret"
            result = await client.post("/jobs/remote_only", json=invocation)
            assert result.status_code == 200
            assert result.json()["success"] is True
            catalog = await client.get("/jobs", params={"target": "remote.test:1024"})
            assert catalog.status_code == 200
            assert [item["name"] for item in catalog.json()["answer"]["items"]] == ["remote_only"]
            events = await client.post("/jobs/remote_only/events", json=invocation)
            assert events.status_code == 200
            assert '"kind": "result"' in events.text
            assert '"success": true' in events.text
            for path in ("/jobs/remote_only", "/jobs/remote_only/events"):
                result = await client.post(path, json={"target": "unconfigured.test:1024"})
                assert result.status_code == 422
            assert (await client.get("/jobs", params={"target": "unconfigured.test:1024"})).status_code == 422
            for path in ("/jobs/remote_only", "/jobs"):
                result = (
                    await client.get(path, params={"target": "remote.test:1025"})
                    if path == "/jobs"
                    else await client.post(path, json={"target": "remote.test:1025"})
                )
                assert result.status_code == 502
                assert "Invalid bearer token" in result.json()["detail"]
            events = await client.post("/jobs/remote_only/events", json={"target": "remote.test:1025"})
            assert events.status_code == 200
            assert '"kind": "result"' in events.text
            assert '"success": false' in events.text
            assert "Invalid bearer token" in events.text
