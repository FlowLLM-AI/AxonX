"""Verify HTTP transport policy, shared Job exposure, and owned resource cleanup."""

import json
import os
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastmcp import Client as McpClient

from axonx.app.components.job.base import RESPONSE_CALLBACKS
from axonx.app.components.registry import provider
from axonx.app.components.service.http.jobs import JobRoutes
from axonx.app.components.service.http.middleware import ResponseCompletionMiddleware
from axonx.app.components.service.http.studio import mount_studio
from axonx.app.core.application import Application
from axonx.app.steps.base import BaseStep
from axonx.client.config import AXONX_SERVICE_TARGET, PROTOCOL_CLI_REQUEST_HEADER, PROTOCOL_FILE_NAME_HEADER
from axonx.client.events import LogEvent, ResultEvent


@pytest.fixture
def make_app(tmp_path):
    @provider("http_echo")
    class EchoStep(BaseStep):
        async def execute(self):
            self.response.answer = {"job": self.kwargs["marker"], "arguments": dict(self.context)}

    def make(*, token="secret", **options):
        jobs = {
            name: {
                "steps": [{"backend": "http_echo", "marker": name}],
                "parameters": {"properties": {"value": {"type": "integer"}}},
                "requires_auth": name == "private",
                "enable_serve": name != "hidden",
                "enable_stream": name != "ordinary",
            }
            for name in ("echo", "private", "hidden", "ordinary")
        }
        return Application(
            providers=(EchoStep,),
            workspace_dir=str(tmp_path),
            log_to_console=False,
            log_to_file=False,
            jobs=jobs,
            service={"backend": "http", "token": token, "web_enabled": False},
            **options,
        )

    return make


@pytest.mark.parametrize("token", [None, "secret"])
async def test_json_sse_and_mcp_share_the_public_job_policy(make_app, token):
    app = make_app(token=token)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    mcp_server = JobRoutes(app, authenticated=token is not None).create_mcp_server()
    async with app, McpClient(mcp_server) as mcp:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app.context.service.build_service(app)),
            base_url="http://test",
            headers=headers,
        ) as client:
            catalog = (await client.get("/jobs")).json()["answer"]
            expected = {"echo", "ordinary"} | ({"private"} if token else set())
            assert {item["name"] for item in catalog["items"]} == expected
            assert {tool.name for tool in await mcp.list_tools()} == expected
            for name in app.context.jobs:
                response = await client.post(f"/jobs/{name}", json={"arguments": {"value": 2}})
                assert response.status_code == (200 if name in expected else 404)
                stream = await client.post(f"/jobs/{name}/events", json={"arguments": {"value": 2}})
                assert stream.status_code == (200 if name in expected and name != "ordinary" else 404)


async def test_mcp_binds_each_job_without_consuming_business_argument_names(make_app):
    app = make_app()
    arguments = {"value": 3, "name": "business", "self": "caller", "arguments": {"nested": True}}
    async with app, McpClient(JobRoutes(app, authenticated=True).create_mcp_server()) as client:
        for name in ("echo", "ordinary"):
            result = await client.call_tool(name, arguments)
            assert result.structured_content["success"]
            assert result.structured_content["answer"] == {"job": name, "arguments": arguments}


@pytest.mark.parametrize("suffix", ["", "/events"])
def test_job_validation_happens_before_the_response_starts(make_app, suffix):
    app = make_app()
    with TestClient(app.context.service.build_service(app), headers={"Authorization": "Bearer secret"}) as client:
        for payload in ({"arguments": {"value": "wrong"}}, {"arguments": {}, "system": {}}, {"target": "unknown:1024"}):
            response = client.post(f"/jobs/echo{suffix}", json=payload)
            assert response.status_code == 422
            assert "application/json" in response.headers["content-type"]
        assert client.post(f"/jobs/missing{suffix}", json={}).status_code == 404


@pytest.mark.parametrize("ending", ["result", "error", "empty"])
def test_sse_sends_one_terminal_result_and_closes_its_source(make_app, monkeypatch, ending):
    app = make_app()
    closed = []

    async def events(*_args, **_kwargs):
        try:
            yield LogEvent(content="中文\noutput", channel="stdout")
            if ending == "error":
                raise ValueError("stream failed")
            if ending == "result":
                yield ResultEvent(answer=42)
                pytest.fail("Read beyond the terminal result")
        finally:
            closed.append(True)

    monkeypatch.setattr(app, "stream_job", events)
    with TestClient(app.context.service.build_service(app), headers={"Authorization": "Bearer secret"}) as client:
        response = client.post("/jobs/echo/events", json={})
    assert response.status_code == 200
    frames = [
        json.loads(line.removeprefix("data: ")) for line in response.text.splitlines() if line.startswith("data: ")
    ]
    assert [event["kind"] for event in frames] == ["log", "result"]
    assert frames[0]["content"] == "中文\noutput"
    assert frames[-1]["success"] == (ending == "result")
    assert closed == [True]


@pytest.mark.parametrize("path", ["/health", "/jobs", "/jobs/echo", "/upload", "/mcp", "/mcp/nested"])
def test_authentication_covers_every_protocol_route(make_app, path):
    app = make_app()
    with TestClient(app.context.service.build_service(app)) as client:
        assert client.get(path).status_code == 401
        assert client.get(path, headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert client.get("/docs").status_code == 200
        preflight = client.options(path, headers={"Origin": "http://studio", "Access-Control-Request-Method": "POST"})
        assert preflight.status_code == 200


@pytest.mark.parametrize("declared", [None, "1"])
async def test_upload_limits_count_the_actual_stream_and_remove_partial_files(make_app, declared):
    app = make_app(transfer_budget_bytes=4)

    async def content():
        yield b"123"
        yield b"45"

    headers = {"Authorization": "Bearer secret", PROTOCOL_FILE_NAME_HEADER: "large.txt"}
    if declared is not None:
        headers["Content-Length"] = declared
    async with (
        app,
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app.context.service.build_service(app)), base_url="http://test"
        ) as client,
    ):
        response = await client.post("/upload", content=content(), headers=headers)
    assert response.status_code == 413
    assert not [path for path in app.workspace.uploads.root.rglob("*") if path.is_file()]


@pytest.mark.parametrize("declared", ["invalid", "-1"])
def test_upload_rejects_invalid_declared_sizes(make_app, declared):
    app = make_app()
    with TestClient(app.context.service.build_service(app), headers={"Authorization": "Bearer secret"}) as client:
        response = client.post("/upload", content=b"a", headers={"Content-Length": declared})
    assert response.status_code == 400


def test_incomplete_multipart_upload_closes_partial_spools(make_app, monkeypatch):
    import starlette.formparsers as parsers

    app = make_app()
    spools = []
    create_spool = parsers.SpooledTemporaryFile

    def track_spool(*args, **kwargs):
        spool = create_spool(*args, **kwargs)  # pylint: disable=consider-using-with
        spools.append(spool)
        return spool

    monkeypatch.setattr(parsers, "SpooledTemporaryFile", track_spool)
    body = b'--test\r\nContent-Disposition: form-data; name="file"; filename="a.txt"\r\n\r\nincomplete'
    with TestClient(app.context.service.build_service(app), headers={"Authorization": "Bearer secret"}) as client:
        response = client.post("/upload", content=body, headers={"Content-Type": "multipart/form-data; boundary=test"})
    assert response.status_code == 400
    assert spools and all(spool.closed for spool in spools)


@pytest.mark.parametrize("previous", [None, "http://previous:1024"])
def test_lifespan_restores_the_target_even_if_shutdown_notification_fails(make_app, monkeypatch, previous):
    if previous is None:
        monkeypatch.delenv(AXONX_SERVICE_TARGET, raising=False)
    else:
        monkeypatch.setenv(AXONX_SERVICE_TARGET, previous)
    app = make_app()

    def fail_shutdown():
        raise RuntimeError("shutdown notification failed")

    monkeypatch.setattr(app.context.service, "request_shutdown", fail_shutdown)
    with pytest.raises(RuntimeError, match="shutdown notification failed"):
        with TestClient(app.context.service.build_service(app)):
            assert os.environ[AXONX_SERVICE_TARGET] == app.context.service.local_target
    assert os.environ.get(AXONX_SERVICE_TARGET) == previous
    assert not app.is_started


@pytest.mark.parametrize("inherited,complete", [(False, False), (False, True), (True, True)])
async def test_response_callbacks_wait_for_the_owning_response(inherited, complete):
    sent, called = [], []
    parent = []
    request_id = "owned-cli"
    service = SimpleNamespace(cli_callbacks={request_id: parent} if inherited else {})

    async def downstream(_scope, _receive, send):
        RESPONSE_CALLBACKS.get().append(lambda: called.append(len(sent)))
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"part", "more_body": not complete})

    async def send(message):
        assert not called
        sent.append(message)

    scope = {"type": "http", "headers": [(PROTOCOL_CLI_REQUEST_HEADER.lower().encode(), request_id.encode())]}
    await ResponseCompletionMiddleware(downstream, service)(scope, None, send)
    assert RESPONSE_CALLBACKS.get() is None
    assert called == ([2] if complete and not inherited else [])
    if inherited:
        assert len(parent) == 1
        parent[0]()
        assert called == [2]


def test_studio_serves_relative_roots_and_handles_removed_assets(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = Path("studio")
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text("<html>Studio</html>")
    (root / "robots.txt").write_text("robots")
    outside = tmp_path / "private.txt"
    outside.write_text("private")
    (root / "outside.txt").symlink_to(outside)
    server = FastAPI()

    @server.get("/health")
    async def health():
        return {"running": True}

    mount_studio(server, root)
    with TestClient(server) as client:
        assert client.get("/robots.txt").text == "robots"
        for path in ("/nested/page", "/outside.txt"):
            response = client.get(path)
            assert response.text == "<html>Studio</html>"
            assert "no-store" in response.headers["cache-control"]
        (root / "assets").rmdir()
        assert client.get("/assets/app.js").status_code == 503
        (root / "index.html").unlink()
        assert client.get("/nested/page").status_code == 503
        assert client.get("/health").json() == {"running": True}
