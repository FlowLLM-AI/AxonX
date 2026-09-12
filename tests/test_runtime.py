"""Task runtime, plugin, worker, and service integration tests."""

# Several tests intentionally define invalid implementations or inspect internal behavior.
# pylint: disable=invalid-overridden-method,missing-class-docstring
# pylint: disable=missing-function-docstring,protected-access,unused-variable,wrong-import-order

import asyncio
import json
import os
from pathlib import Path
import signal
import pytest
from axonx import Application, BaseComponent, BaseTask
from axonx.config import resolve_app_config
from axonx.components import R
from axonx.constants import (
    AXONX_DEFAULT_CONNECT_HOST,
    AXONX_DEFAULT_PORT,
    AXONX_SERVICE_INFO,
    AXONX_TASK_WORKSPACE_DIR,
)
from axonx.plugin.manifest import parse_plugin_manifest
from axonx.enumeration import TaskState, TaskType
from axonx.schema import PluginManifest, TaskStatus


def application(tmp_path, **manager):
    config = resolve_app_config(workspace_dir=str(tmp_path))
    config.setdefault("environment", {})["PYTHONPATH"] = str(Path(__file__).parent)
    config["components"]["task_manager"]["default"].update(**manager)
    return Application(**config)


async def test_task_manager_starts_exec_with_original_arguments(monkeypatch, tmp_path, capsys):
    calls = []

    class Process:
        pid = 12345
        returncode = 0

        def __init__(self):
            self.stderr = asyncio.StreamReader()
            self.stderr.feed_eof()

        async def wait(self):
            return self.returncode

    async def create_subprocess_exec(*command, **options):
        calls.append((command, options))
        return Process()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_subprocess_exec)
    monkeypatch.setattr(os, "killpg", lambda *_args: pytest.fail("manager close must not signal task processes"))
    monkeypatch.setenv("AXONX_PARENT_ONLY", "not inherited")
    monkeypatch.setenv(AXONX_SERVICE_INFO, '{"host":"service.internal","port":4321}')
    argv = ["--task", "sales", "--output", "result file.parquet"]
    async with application(tmp_path) as app:
        manager = app.get_component("task_manager")
        await manager.submit(argv)
        await asyncio.gather(*manager._process_monitors)

    command, options = calls[0]
    assert command[1:] == ("-m", "axonx.cli", "exec", *argv)
    assert options["start_new_session"] is True
    assert "AXONX_PARENT_ONLY" not in options["env"]
    assert options["env"][AXONX_SERVICE_INFO] == '{"host":"service.internal","port":4321}'
    assert options["env"][AXONX_TASK_WORKSPACE_DIR] == str(tmp_path.resolve())
    assert options["env"]["PYTHONPATH"] == str(Path(__file__).parent)
    assert options["stderr"] == asyncio.subprocess.PIPE
    success_log = capsys.readouterr().err
    assert "Task process 12345 (sales) completed successfully" in success_log


async def test_task_manager_logs_worker_stderr_on_failure(monkeypatch, tmp_path, capsys):
    class Process:
        pid = 23456
        returncode = 2

        def __init__(self):
            self.stderr = asyncio.StreamReader()
            self.stderr.feed_data(b"ValidationError: invalid start_date\n")
            self.stderr.feed_eof()

        async def wait(self):
            return self.returncode

    async def create_subprocess_exec(*_command, **_options):
        return Process()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_subprocess_exec)
    async with application(tmp_path) as app:
        manager = app.get_component("task_manager")
        await manager.submit(["--task", "download_tushar_task"])
        await asyncio.gather(*manager._process_monitors)

    error = capsys.readouterr().err
    assert "ValidationError: invalid start_date" in error
    assert "download_tushar_task" in error
    assert "exited with code 2" in error


async def test_lifecycle_rollback(tmp_path):
    events = []

    class Good(BaseComponent):
        component_type = "test"

        async def _start(self):
            events.append("start")

        async def _close(self):
            events.append("close")

    class Bad(Good):
        async def _start(self):
            raise ValueError("startup")

    with R.preserve(allow_mutation=True):
        R.register(Good, "good")
        R.register(Bad, "bad")
        app = Application(
            workspace_dir=str(tmp_path),
            components={"test": {"a": {"backend": "good"}, "b": {"backend": "bad"}}},
        )
    with pytest.raises(ValueError):
        await app.start()
    assert events == ["start", "close", "close"]
    assert not app.is_started


def test_task_has_no_components():
    class ProbeTask(BaseTask):
        task_type = TaskType.ANALYSIS

        def build_task_steps(self):
            return ()

    assert not hasattr(ProbeTask({}), "app_context")


def test_plugin_manifest_tasks_only():
    manifest = parse_plugin_manifest("tasks:\n  demo: package.module:Task\n", "test")
    assert isinstance(manifest, PluginManifest)
    assert manifest.tasks == {"demo": "package.module:Task"}
    with pytest.raises(ValueError, match="backends"):
        parse_plugin_manifest("backends: {}\n", "test")


@pytest.mark.parametrize(
    "text",
    ["tasks: []\n", "tasks:\n  '': package.module:Task\n", "tasks:\n  task: ''\n", "tasks:\n  task: 1\n"],
)
def test_plugin_manifest_rejects_invalid_schema(text):
    with pytest.raises(ValueError, match="Plugin 'test' manifest is invalid"):
        parse_plugin_manifest(text, "test")


def test_plugin_manifest_defaults_and_normalizes_task_strings():
    manifest = parse_plugin_manifest("tasks:\n  ' sales ': ' package.module:Task '\n", "test")

    assert manifest.tasks == {"sales": "package.module:Task"}


def test_http_client_discovers_service_from_environment(monkeypatch, capsys):
    from axonx.components.client import HttpClient, McpClient

    monkeypatch.setenv(AXONX_SERVICE_INFO, '{"host": "service.internal", "port": 4321}')
    assert HttpClient().url == "http://service.internal:4321"
    assert McpClient().url == "http://service.internal:4321/mcp"
    assert HttpClient(host_ip="explicit.example", host_port=8443).url == "http://explicit.example:8443"
    assert HttpClient(host_ip=AXONX_DEFAULT_CONNECT_HOST, host_port=AXONX_DEFAULT_PORT).url == "http://127.0.0.1:1024"
    assert HttpClient(host_ip="2001:db8::1", host_port=8443).url == "http://[2001:db8::1]:8443"

    monkeypatch.setenv(AXONX_SERVICE_INFO, '{"host": "missing-port"}')
    assert HttpClient().url == f"http://{AXONX_DEFAULT_CONNECT_HOST}:{AXONX_DEFAULT_PORT}"
    assert f"Invalid {AXONX_SERVICE_INFO} value" in capsys.readouterr().err


@pytest.mark.parametrize("client_name", ["HttpClient", "McpClient"])
async def test_remote_clients_require_start(client_name):
    from axonx.components import client as client_module

    client = getattr(client_module, client_name)(host_ip="service.example", host_port=443)

    with pytest.raises(RuntimeError, match="Client is not started"):
        await client.list_jobs()


async def test_http_service_publishes_service_info(monkeypatch):
    from axonx.components import HttpService

    previous = '{"host": "previous", "port": 1234}'
    monkeypatch.setenv(AXONX_SERVICE_INFO, previous)
    app = Application(app_name="Configured AxonX")
    service = HttpService(host="127.0.0.2", port=4321)
    server = service.build_service(app)

    assert server.title == "Configured AxonX"
    async with server.router.lifespan_context(server):
        assert json.loads(os.environ[AXONX_SERVICE_INFO]) == {"host": "127.0.0.2", "port": 4321}
        assert app.is_started

    assert os.environ[AXONX_SERVICE_INFO] == previous
    assert not app.is_started


async def test_http_service_advertises_loopback_for_default_wildcard_bind(
    monkeypatch,
):
    from axonx.components import HttpService

    monkeypatch.delenv(AXONX_SERVICE_INFO, raising=False)
    app = Application()
    service = HttpService()
    server = service.build_service(app)

    assert service.host == "0.0.0.0"
    async with server.router.lifespan_context(server):
        assert json.loads(os.environ[AXONX_SERVICE_INFO]) == {
            "host": AXONX_DEFAULT_CONNECT_HOST,
            "port": AXONX_DEFAULT_PORT,
        }

    assert AXONX_SERVICE_INFO not in os.environ


async def test_http_and_mcp_expose_the_same_jobs():
    import httpx
    from fastmcp import Client
    from axonx.components import HttpService

    app = Application(
        jobs={
            "visible": {
                "description": "A visible job",
                "parameters": {"type": "object", "properties": {"value": {"type": "string"}}},
            },
            "hidden": {"enable_serve": False},
            "scheduled": {"backend": "cron", "cron": "0 * * * *"},
        },
    )
    service = HttpService()
    assert service.host == "0.0.0.0"
    assert service.port == AXONX_DEFAULT_PORT
    server = service.build_service(app)

    async with server.router.lifespan_context(server):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server), base_url="http://test") as http_client:
            response = await http_client.get("/jobs")
            assert response.status_code == 200
            assert [job["name"] for job in response.json()] == ["visible"]
            assert response.json()[0]["inputSchema"]["properties"] == {
                "value": {"type": "string"},
                "remote_ip": {
                    "type": "string",
                    "description": "Optional IP of a configured remote AxonX node.",
                },
            }
            assert (await http_client.post("/jobs/hidden", json={})).status_code == 404
            invalid = await http_client.post("/jobs/visible", json={"value": 1})
            assert invalid.status_code == 422

        async with Client(service.mcp_server) as mcp_client:
            tools = await mcp_client.list_tools()
            assert [tool.name for tool in tools] == ["visible"]
            assert tools[0].description == "A visible job"
            result = await mcp_client.call_tool("visible", {"value": "ok"})
            assert result.data.success


async def test_mcp_client_uses_common_job_interface(monkeypatch):
    from types import SimpleNamespace
    import fastmcp
    from mcp.types import Tool
    from axonx.components.client import McpClient
    from axonx.schema import Response

    class Client:
        healthy = True

        def __init__(self, source, **options):
            assert source == "http://service.example:443/mcp"
            assert options["auth"] is None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def list_tools(self):
            return [
                Tool(
                    name="demo",
                    description="Demo",
                    inputSchema={"type": "object", "properties": {}},
                    outputSchema=Response.model_json_schema(),
                ),
            ]

        async def ping(self):
            if not self.healthy:
                raise OSError("unreachable")
            return True

        async def call_tool(self, name, arguments):
            assert (name, arguments) == ("demo", {"value": 1})
            return SimpleNamespace(data=Response(answer="done"))

    monkeypatch.setattr(fastmcp, "Client", Client)

    async with McpClient(host_ip="service.example", host_port=443) as client:
        assert await client.health()
        client.client.healthy = False
        assert not await client.health()
        jobs = await client.list_jobs()
        response = await client.run_job("demo", value=1)

    assert jobs[0].name == "demo"
    assert jobs[0].input_schema["type"] == "object"
    assert response.answer == "done"


async def test_concurrent_job_contexts(tmp_path):
    app = Application(
        workspace_dir=str(tmp_path),
        jobs={"demo": {"steps": [{"backend": "version_step"}, {"backend": "demo_step"}]}},
    )
    async with app:
        results = await asyncio.gather(*(app.run_job("demo") for _ in range(5)))
        assert all(r.answer.startswith("Demo running on AxonX ") for r in results)
        assert all(r.answer.endswith(r.metadata["version"]) for r in results)
        assert len({id(r) for r in results}) == 5


async def test_submit_validation_and_status_snapshot(tmp_path):
    async with application(tmp_path) as app:
        manager = app.get_component("task_manager")
        status = TaskStatus(
            task_id="analysis#snapshot",
            task_type=TaskType.ANALYSIS,
            state=TaskState.SUCCEEDED,
            result={"value": 2},
        )
        await manager.set_status(status.task_id, status)
        record = await manager.get_status(status.task_id)
        record.result["value"] = -1
        assert (await manager.get_status(status.task_id)).result["value"] == 2
        assert json.loads(manager.status_path.read_text())["tasks"] == [status.model_dump(mode="json")]


async def test_cancel_returns_whether_signal_was_sent(monkeypatch, tmp_path):
    signals = []
    pid = 12345

    monkeypatch.setattr(os, "killpg", lambda pid, sig: signals.append((pid, sig)))
    async with application(tmp_path) as app:
        manager = app.get_component("task_manager")
        status = TaskStatus(
            task_id="analysis#cancel",
            task_type=TaskType.ANALYSIS,
            state=TaskState.RUNNING,
            pid=pid,
        )
        await manager.set_status(status.task_id, status)

        assert await manager.cancel(status.task_id) is True
        record = await manager.get_status(status.task_id)
        assert record.state == TaskState.CANCELLED
        assert record.exit_code == 130
        assert record.finished_at is not None

    assert signals == [(pid, signal.SIGKILL)]


async def test_cancel_returns_false_without_a_live_managed_process(tmp_path):
    def missing_process(_pid, _sig):
        raise ProcessLookupError

    async with application(tmp_path) as app:
        manager = app.get_component("task_manager")
        status = TaskStatus(
            task_id="analysis#not-running",
            task_type=TaskType.ANALYSIS,
            state=TaskState.RUNNING,
            pid=12345,
        )
        await manager.set_status(status.task_id, status)
        with pytest.MonkeyPatch.context() as monkeypatch:
            monkeypatch.setattr(os, "killpg", missing_process)
            assert await manager.cancel(status.task_id) is False

        assert (await manager.get_status(status.task_id)).state == TaskState.RUNNING


async def test_unfinished_history_is_loaded_without_rewriting(tmp_path):
    directory = tmp_path / "task_manager"
    directory.mkdir(parents=True)
    (directory / "status.json").write_text(
        json.dumps(
            {
                "version": 1,
                "tasks": [
                    {
                        "task_id": "old",
                        "task_type": "analysis",
                        "created_at": "2024-01-01T00:00:00Z",
                        "state": "running",
                        "pid": os.getpid(),
                    },
                ],
            },
        ),
    )
    async with application(tmp_path) as app:
        record = await app.get_component("task_manager").get_status("old")
        assert record.state == "running"
        assert record.pid == os.getpid()


async def test_task_manager_replaces_status_from_another_version_on_close(tmp_path):
    directory = tmp_path / "task_manager"
    directory.mkdir(parents=True)
    status_path = directory / "status.json"
    status_path.write_text(
        json.dumps(
            {
                "version": 1,
                "tasks": [
                    {
                        "task_id": "old",
                        "task_type": "analysis",
                        "state": "succeeded",
                    },
                ],
            },
        ),
    )

    async with application(tmp_path, version=2) as app:
        manager = app.get_component("task_manager")
        assert manager.task_manager_dir == directory
        assert await manager.list_task_ids() == []

    assert json.loads(status_path.read_text()) == {"version": 2, "tasks": []}


async def test_task_manager_logs_and_ignores_invalid_status(tmp_path, capsys):
    directory = tmp_path / "task_manager"
    directory.mkdir(parents=True)
    status_path = directory / "status.json"
    status_path.write_text(
        json.dumps(
            {
                "version": 1,
                "tasks": {"old": {"task_id": "old", "task_type": "analysis"}},
            },
        ),
    )

    async with application(tmp_path) as app:
        manager = app.get_component("task_manager")
        assert await manager.list_task_ids() == []
        assert json.loads(status_path.read_text())["tasks"] == {"old": {"task_id": "old", "task_type": "analysis"}}

    assert "Failed to load task status" in capsys.readouterr().err
    assert json.loads(status_path.read_text())["tasks"] == []


async def test_http_service_installs_task_plugin_wheel(monkeypatch, tmp_path):
    import httpx

    from axonx.components import HttpService
    from axonx.plugin.artifact import build_wheel, inspect_wheel, source_sha256

    source = Path("plugins/polars-demo").resolve()
    wheel = build_wheel(source, tmp_path / "build" / source_sha256(source))
    artifact = inspect_wheel(wheel)
    app = Application(
        workspace_dir=str(tmp_path / "workspace"),
        components={
            "plugin": {"default": {"backend": "local", "allow_remote_install": True, "install_token": "secret"}},
        },
        jobs={"list_plugins": {"steps": [{"backend": "list_plugins_step"}]}},
    )
    plugin = app.get_component("plugin")
    monkeypatch.setattr(plugin, "_install", lambda _artifact: None)
    server = HttpService().build_service(app)

    async with server.router.lifespan_context(server):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server), base_url="http://test") as client:
            response = await client.post(
                "/plugins",
                content=wheel.read_bytes(),
                headers={
                    "authorization": "Bearer secret",
                    "x-wheel-filename": wheel.name,
                    "x-wheel-sha256": artifact.sha256,
                },
            )
            plugins = await client.post("/jobs/list_plugins", json={})

    assert response.status_code == 200
    assert response.json()["tasks"] == {"sales": "axonx_polars_demo.sales:SalesTask"}
    assert plugins.json()["answer"][0]["wheel_sha256"] == artifact.sha256
