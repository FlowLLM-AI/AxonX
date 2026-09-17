"""Shell Job execution and remote routing tests."""

import pytest

from axonx import Application
from axonx.components.client import HttpClient
from axonx.config import resolve_app_config
from axonx.schema import Response
from axonx.utils.cli import parse_command


def test_shell_cli_arguments():
    local, _ = parse_command(["shell", "--command", "hostname"])
    remote, _ = parse_command(
        ["shell", "--remote-ip", "11.160.132.45", "--command", "hostname"]
    )

    assert local.action == remote.action == "shell"
    assert local.arguments["command"] == "hostname"
    assert "remote_ip" not in local.arguments
    assert remote.arguments["remote_ip"] == "11.160.132.45"
    assert remote.arguments["command"] == "hostname"


@pytest.mark.asyncio
async def test_shell_runs_locally():
    app = Application(**resolve_app_config(log_config=False))
    async with app:
        response = await app.run_job("shell", command="printf 'hello\\n'")

    assert response.success
    assert response.answer == {"stdout": "hello\n", "stderr": "", "exit_code": 0}


@pytest.mark.asyncio
async def test_shell_reports_nonzero_exit():
    app = Application(**resolve_app_config(log_config=False))
    async with app:
        response = await app.run_job("shell", command="printf 'failed' >&2; exit 7")

    assert not response.success
    assert response.answer == {"stdout": "", "stderr": "failed", "exit_code": 7}


@pytest.mark.asyncio
async def test_shell_times_out():
    app = Application(**resolve_app_config(log_config=False))
    async with app:
        response = await app.run_job("shell", command="sleep 2", timeout=0.05)

    assert not response.success
    assert response.answer["exit_code"] is None
    assert "timed out" in response.answer["stderr"]


@pytest.mark.asyncio
async def test_shell_routes_to_configured_remote(monkeypatch):
    expected = Response(answer={"stdout": "remote\n", "stderr": "", "exit_code": 0})

    async def run_job(client, name, **kwargs):
        assert client.url == "http://11.160.132.45:1024"
        assert name == "shell"
        assert kwargs == {"command": "hostname"}
        return expected

    monkeypatch.setattr(HttpClient, "run_job", run_job)
    app = Application(**resolve_app_config(log_config=False))
    async with app:
        response = await app.run_job("shell", remote_ip="11.160.132.45", command="hostname")

    assert response is expected
