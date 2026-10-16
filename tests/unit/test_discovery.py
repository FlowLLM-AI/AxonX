"""Discovery must describe the selected service and keep diagnostics read-only."""

import importlib
import json

import httpx
import pytest
import yaml
from fastmcp import Client

from axonx.components.service.http.jobs import create_mcp_server
from axonx.components.client import HttpClient
from axonx.core import Application
from axonx.plugin_kit.models import PluginInfo


def make_app(tmp_path, *, token="service-secret"):
    from importlib.resources import files

    defaults = yaml.safe_load(files("axonx.config").joinpath("default.yaml").read_text())
    return Application(
        workspace_dir=str(tmp_path / "missing" / "workspace"),
        log_to_console=False,
        log_to_file=False,
        service={"backend": "http", "token": token, "web_enabled": False},
        jobs={
            **{name: defaults["jobs"][name] for name in ("help", "diagnose", "python")},
            "custom": {
                "description": "Plugin-defined operation",
                "parameters": {"type": "object", "properties": {"count": {"type": "integer"}}, "required": ["count"]},
                "steps": [{"backend": "version_step"}],
            },
            "hidden": {"enable_serve": False, "steps": [{"backend": "version_step"}]},
        },
    )


@pytest.mark.asyncio
async def test_help_http_matches_catalog_and_returns_live_schemas(tmp_path):
    app = make_app(tmp_path)
    server = app.context.service.build_service(app)
    async with (
        server.router.lifespan_context(server),
        HttpClient(token="service-secret", transport=httpx.ASGITransport(app=server)) as client,
    ):
        catalog = await client.list_jobs()
        response = await client.run_job("help")
        assert response.success
        assert {item["name"] for item in response.answer["jobs"]} == {job.name for job in catalog}
        detail = await client.run_job("help", {"job": "custom"})
        assert detail.success
        assert detail.answer["job"] == app.context.jobs["custom"].info.model_dump(mode="json")
        assert detail.answer["job"]["input_schema"]["required"] == ["count"]
        python_help = await client.run_job("help", {"job": "python"})
        assert python_help.answer["job"]["input_schema"]["properties"]["timeout"]["maximum"] == 300
        for name in ("hidden", "not-installed"):
            unknown = await client.run_job("help", {"job": name})
            assert not unknown.success
            assert "Unknown public Job" in unknown.answer


@pytest.mark.asyncio
async def test_help_respects_auth_filter_and_is_available_as_mcp_tool(tmp_path):
    app = make_app(tmp_path, token=None)
    public = {name: job for name, job in app.context.jobs.items() if job.is_public(authenticated=False)}
    async with app, Client(create_mcp_server(app, public)) as client:
        result = await client.call_tool("help", {})
        assert result.data.success
        assert [item["name"] for item in result.data.answer["jobs"]] == ["help"]

    server = app.context.service.build_service(app)
    async with server.router.lifespan_context(server), HttpClient(transport=httpx.ASGITransport(app=server)) as client:
        response = await client.run_job("help")
        assert response.success
        assert [item["name"] for item in response.answer["jobs"]] == ["help"]
        protected = await client.run_job("help", {"job": "diagnose"})
        assert not protected.success


@pytest.mark.asyncio
async def test_diagnose_reports_fingerprints_and_never_returns_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("AXONX_SERVICE_TOKEN", "super-private-token")
    monkeypatch.setenv("AXONX_TUSHARE_TOKEN", "market-secret")
    monkeypatch.delenv("AXONX_TARGET_TOKEN", raising=False)
    monkeypatch.setattr(
        "axonx.steps.machine.diagnostics.list_installed_plugins",
        lambda: [PluginInfo(distribution="example", version="1", content_sha256="a" * 64, error="broken plugin")],
    )
    monkeypatch.setattr("axonx.steps.machine.diagnostics.restart_required", lambda: True)
    app = make_app(tmp_path)
    async with app.context.jobs["diagnose"]:
        response = await app.context.dispatcher.run("diagnose")
    assert response.success
    answer = response.model_dump(mode="json")["answer"]
    assert answer["python"]["executable"]
    assert answer["axonx"]["version"]
    assert answer["service_auth_enabled"] is True
    assert answer["restart_required"] is True
    assert answer["plugins"][0]["content_sha256"] == "a" * 64
    assert answer["plugins"][0]["error"] == "broken plugin"
    assert answer["credentials_configured"] == {
        "AXONX_SERVICE_TOKEN": True,
        "AXONX_TARGET_TOKEN": False,
        "AXONX_TUSHARE_TOKEN": True,
    }
    assert answer["workspace"]["exists"] is False
    assert answer["workspace"]["disk"]["path"] == str(tmp_path)
    assert answer["workspace"]["disk"]["free_bytes"] >= 0
    assert not app.workspace_path.exists()
    serialized = json.dumps(answer)
    for secret in ("super-private-token", "market-secret", "service-secret"):
        assert secret not in serialized


def test_cli_help_is_remote_but_usage_is_offline(monkeypatch, capsys):
    cli = importlib.import_module("axonx.cli.main")
    calls = []
    monkeypatch.setattr(cli, "_run_remote_job", lambda command, options: calls.append((command, options)) or 0)
    assert cli.main(["help", "--job", "python", "--target", "node-b:1024"]) == 0
    command, options = calls.pop()
    assert command.action == "help"
    assert command.arguments["job"] == "python"
    assert options.target == "http://node-b:1024"
    for arguments in ([], ["--help"], ["-h"]):
        assert cli.main(arguments) == 0
    assert not calls
    assert "Usage:" in capsys.readouterr().out
