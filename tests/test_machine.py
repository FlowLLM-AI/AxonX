"""Machine resource collection and discovery tests."""

# Tests intentionally inspect collectors and use lightweight callback fakes.
# pylint: disable=missing-function-docstring,protected-access,unused-argument

import json
from types import SimpleNamespace

import httpx
import pytest

from axonx import Application
from axonx.components.client import HttpClient
from axonx.components.machine import LocalMachineComponent
from axonx.components.service import HttpService
from axonx.schema import Response


def test_collect_local_machine_info(monkeypatch):
    component = LocalMachineComponent(cpu_sample_interval=0)
    monkeypatch.setattr("axonx.components.machine.local.psutil.cpu_count", lambda logical: 8)
    monkeypatch.setattr("axonx.components.machine.local.psutil.cpu_percent", lambda interval: 25.0)
    monkeypatch.setattr(
        "axonx.components.machine.local.psutil.virtual_memory",
        lambda: SimpleNamespace(total=1_000, used=400, available=550, percent=40.0),
    )
    monkeypatch.setattr(component, "_axonx_version", lambda: "1.2.3")
    monkeypatch.setattr(component, "_git_commit", lambda: "abc123")
    monkeypatch.setattr(component, "_gpu_info", lambda: [{"index": 0}])

    assert component._collect_local_info() == {
        "axonx": {"version": "1.2.3", "git_commit": "abc123"},
        "cpu": {
            "total_cores": 8,
            "physical_cores": 8,
            "usage_percent": 25.0,
            "used_cores": 2.0,
        },
        "memory": {
            "total_bytes": 1_000,
            "used_bytes": 400,
            "available_bytes": 550,
            "usage_percent": 40.0,
        },
        "gpus": [{"index": 0}],
    }


def test_parse_nvidia_smi_output(monkeypatch):
    output = "0, GPU-1, NVIDIA A100, 81920, 40960, 40960, 75\n"
    monkeypatch.setattr("axonx.components.machine.local.platform.system", lambda: "Linux")
    monkeypatch.setattr(
        "axonx.components.machine.local.shutil.which",
        lambda command: f"/usr/bin/{command}" if command == "nvidia-smi" else None,
    )
    monkeypatch.setattr(
        "axonx.components.machine.local.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(stdout=output),
    )

    assert LocalMachineComponent._gpu_info() == [
        {
            "vendor": "nvidia",
            "index": 0,
            "uuid": "GPU-1",
            "name": "NVIDIA A100",
            "memory_total_bytes": 81920 * 1024**2,
            "memory_used_bytes": 40960 * 1024**2,
            "memory_available_bytes": 40960 * 1024**2,
            "memory_usage_percent": 50.0,
            "usage_percent": 75.0,
        },
    ]


def test_macos_gpu_info_is_null(monkeypatch):
    monkeypatch.setattr("axonx.components.machine.local.platform.system", lambda: "Darwin")
    assert LocalMachineComponent._gpu_info() is None


def test_parse_amd_gpu_info(monkeypatch):
    output = json.dumps(
        {
            "card0": {
                "Card series": "AMD Radeon PRO",
                "Unique ID": "GPU-AMD-1",
                "VRAM Total Memory (B)": "1000",
                "VRAM Total Used Memory (B)": "250",
                "GPU use (%)": "40",
            },
        },
    )
    monkeypatch.setattr(
        "axonx.components.machine.local.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(stdout=output),
    )

    assert LocalMachineComponent._amd_gpu_info() == [
        {
            "vendor": "amd",
            "index": 0,
            "uuid": "GPU-AMD-1",
            "name": "AMD Radeon PRO",
            "memory_total_bytes": 1000,
            "memory_used_bytes": 250,
            "memory_available_bytes": 750,
            "memory_usage_percent": 25.0,
            "usage_percent": 40.0,
        },
    ]


@pytest.mark.parametrize(
    "node",
    [
        {"host_ip": "node.internal", "host_port": 8000},
        {"host_ip": "http://192.168.1.10", "host_port": 8000},
        {"host_ip": "192.168.1.10"},
        {"host_ip": "192.168.1.10", "host_port": 0},
    ],
)
def test_remote_node_requires_ip_and_port(node):
    with pytest.raises(ValueError):
        Application(remote_nodes=[node])


def test_remote_node_ips_are_unique_after_normalization():
    with pytest.raises(ValueError, match="Duplicate remote node IP"):
        Application(
            remote_nodes=[
                {"host_ip": "2001:db8::1", "host_port": 9000},
                {"host_ip": "2001:0db8:0:0:0:0:0:1", "host_port": 9001},
            ],
        )


async def test_application_routes_machine_status_by_ip(monkeypatch):
    expected = {"axonx": {"version": "1.2.3"}, "gpus": []}

    async def run_job(client, name, **kwargs):
        assert client.url == "http://192.168.1.10:9000"
        assert name == "machine_status"
        assert not kwargs
        return Response(answer=expected)

    monkeypatch.setattr(HttpClient, "run_job", run_job)

    app = Application(
        remote_nodes=[{"host_ip": "192.168.1.10", "host_port": 9000}],
        components={"machine": {"default": {"backend": "machine"}}},
        jobs={"machine_status": {"steps": [{"backend": "machine_status_step"}]}},
    )
    async with app:
        response = await app.run_job("machine_status", remote_ip="192.168.1.10")

    assert response.answer == expected


async def test_remote_machine_http_failure_is_propagated(monkeypatch):
    async def run_job(client, name, **kwargs):
        request = httpx.Request("POST", f"{client.url}/jobs/{name}")
        raise httpx.HTTPStatusError(
            "unavailable",
            request=request,
            response=httpx.Response(503, request=request),
        )

    monkeypatch.setattr(HttpClient, "run_job", run_job)
    app = Application(
        remote_nodes=[{"host_ip": "192.168.1.10", "host_port": 9000}],
        jobs={"machine_status": {}},
    )
    async with app:
        with pytest.raises(httpx.HTTPStatusError):
            await app.run_job("machine_status", remote_ip="192.168.1.10")


async def test_machine_status_rejects_unconfigured_remote():
    app = Application(jobs={"machine_status": {}})
    async with app:
        with pytest.raises(ValueError, match="not configured"):
            await app.run_job("machine_status", remote_ip="192.168.1.10")


async def test_list_machines_checks_health_without_machine_component(monkeypatch):
    async def health(client):
        return client.url == "http://192.168.1.10:9000"

    monkeypatch.setattr(HttpClient, "health", health)

    app = Application(
        remote_nodes=[
            {"host_ip": "192.168.1.10", "host_port": 9000},
            {"host_ip": "192.168.1.11", "host_port": 9001},
        ],
        jobs={
            "list_machines": {
                "enable_remote": False,
                "steps": [{"backend": "list_machines_step"}],
            },
        },
    )
    async with app:
        response = await app.run_job("list_machines")
        assert response.answer == [
            {"address": "192.168.1.10:9000", "healthy": True},
            {"address": "192.168.1.11:9001", "healthy": False},
        ]


async def test_http_client_health():
    client = HttpClient(host_ip="192.168.1.10", host_port=9000)
    client.client = httpx.AsyncClient(
        base_url=client.url,
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"running": True})),
    )
    try:
        assert await client.health()
    finally:
        await client.client.aclose()


async def test_http_service_exposes_machine_jobs(monkeypatch):
    app = Application(
        remote_nodes=[{"host_ip": "192.168.1.10", "host_port": 9000}],
        components={"machine": {"default": {"backend": "machine"}}},
        jobs={
            "machine_status": {"steps": [{"backend": "machine_status_step"}]},
            "list_machines": {
                "enable_remote": False,
                "steps": [{"backend": "list_machines_step"}],
            },
        },
    )
    machine = app.get_component("machine")

    async def get_info():
        return {"source": "local", "cpu": {"total_cores": 8}}

    async def run_job(client, name, **kwargs):
        assert client.url == "http://192.168.1.10:9000"
        assert name == "machine_status"
        assert not kwargs
        return Response(answer={"source": "remote", "cpu": {"total_cores": 16}})

    async def health(client):
        return True

    monkeypatch.setattr(machine, "get_info", get_info)
    monkeypatch.setattr(HttpClient, "run_job", run_job)
    monkeypatch.setattr(HttpClient, "health", health)
    server = HttpService().build_service(app)
    async with server.router.lifespan_context(server):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server), base_url="http://test") as client:
            local = await client.post("/jobs/machine_status", json={})
            remote = await client.post("/jobs/machine_status", json={"remote_ip": "192.168.1.10"})
            machines = await client.post("/jobs/list_machines", json={})
            rejected = await client.post("/jobs/list_machines", json={"remote_ip": "192.168.1.10"})

    assert local.json()["answer"]["source"] == "local"
    assert remote.json()["answer"]["source"] == "remote"
    assert machines.json()["answer"] == [{"address": "192.168.1.10:9000", "healthy": True}]
    assert rejected.status_code == 422
