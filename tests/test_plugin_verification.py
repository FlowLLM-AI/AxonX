"""Remote Task submission checks the installed plugin wheel on both nodes."""

import httpx
import pytest

from axonx.components.client import HttpClient
from axonx.plugin import verification


def _response(answer):
    return {"answer": answer, "success": True, "metadata": {}}


@pytest.mark.asyncio
async def test_remote_submit_rejects_mismatched_plugin_before_submission(monkeypatch):
    monkeypatch.setattr(verification, "installed_plugin_for_task", lambda _task: ("axonx-alpha158", "local"))
    requests = []

    def respond(request):
        requests.append(request.url.path)
        return httpx.Response(
            200,
            json=_response(
                [{"distribution": "axonx-alpha158", "tasks": {"alpha158_etl": "target"}, "wheel_sha256": "remote"}],
            ),
        )

    client = HttpClient(host_ip="127.0.0.1", host_port=1024)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond), base_url=client.url) as transport:
        client.client = transport
        with pytest.raises(ValueError, match="Install the plugin locally and deploy"):
            await client.run_job("submit", task="alpha158_etl")

    assert requests == ["/jobs/list_plugins"]


@pytest.mark.asyncio
async def test_remote_submit_succeeds_when_plugin_wheels_match(monkeypatch):
    monkeypatch.setattr(verification, "installed_plugin_for_task", lambda _task: ("axonx-alpha158", "same"))
    requests = []

    def respond(request):
        requests.append(request.url.path)
        answer = (
            [{"distribution": "axonx-alpha158", "tasks": {"alpha158_etl": "target"}, "wheel_sha256": "same"}]
            if request.url.path == "/jobs/list_plugins"
            else {"accepted": True}
        )
        return httpx.Response(200, json=_response(answer))

    client = HttpClient(host_ip="127.0.0.1", host_port=1024)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond), base_url=client.url) as transport:
        client.client = transport
        result = await client.run_job("submit", task="alpha158_etl")

    assert result.answer == {"accepted": True}
    assert requests == ["/jobs/list_plugins", "/jobs/submit"]


@pytest.mark.asyncio
async def test_remote_submit_allows_native_task_without_local_plugin(monkeypatch):
    monkeypatch.setattr(verification, "installed_plugin_for_task", lambda _task: None)

    def respond(request):
        return httpx.Response(200, json=_response([] if request.url.path == "/jobs/list_plugins" else {"accepted": True}))

    client = HttpClient(host_ip="127.0.0.1", host_port=1024)
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond), base_url=client.url) as transport:
        client.client = transport
        result = await client.run_job("submit", task="demo")

    assert result.answer == {"accepted": True}


def test_remote_plugin_requires_verifiable_local_wheel(monkeypatch):
    monkeypatch.setattr(verification, "installed_plugin_for_task", lambda _task: ("axonx-alpha158", None))
    with pytest.raises(ValueError, match="wheel SHA-256 is unavailable"):
        verification.verify_remote_plugin(
            "alpha158_etl",
            [{"distribution": "axonx-alpha158", "tasks": {"alpha158_etl": "target"}, "wheel_sha256": "remote"}],
        )


def test_remote_submit_rejects_missing_managed_wheel(monkeypatch):
    monkeypatch.setattr(verification, "installed_plugin_for_task", lambda _task: ("axonx-alpha158", "local"))
    with pytest.raises(ValueError, match="no managed wheel"):
        verification.verify_remote_plugin("alpha158_etl", [])
