"""Task runtime, plugin, worker, and service integration tests."""

# Several tests intentionally define invalid implementations or inspect internal behavior.
# pylint: disable=invalid-overridden-method,missing-class-docstring
# pylint: disable=missing-function-docstring,protected-access,unused-variable,wrong-import-order

import asyncio
import os
from importlib.metadata import EntryPoint
from pathlib import Path
import pytest
from axonx import Application, BaseComponent, BaseStep
from axonx.config import resolve_app_config
from axonx.components import R
from axonx.constants import AXONX_DEFAULT_URL, AXONX_SERVICE_INFO
from axonx.plugin.manifest import parse_plugin_manifest
from axonx.plugin.runtime import _load_plugin
from axonx.enumeration import TaskState
from axonx.schema import PluginManifest
from task_fixtures import ProbeTask


def application(tmp_path, **manager):
    config = resolve_app_config(workspace_dir=str(tmp_path), plugins=["polars-demo"])
    config.setdefault("environment", {})["PYTHONPATH"] = str(Path(__file__).parent)
    config["components"]["task_manager"]["default"].update(cancel_timeout=0.1, terminate_timeout=0.2, **manager)
    with R.preserve(allow_mutation=True):
        R.register(ProbeTask, "probe")
        return Application(**config)


async def started(manager, run_id):
    async with asyncio.timeout(10):
        while True:
            record = await manager.status(run_id)
            if record.task_steps:
                return record
            if record.state in {TaskState.FAILED, TaskState.LOST}:
                pytest.fail(record.error)
            await asyncio.sleep(0.02)


def assert_dead(pid):
    if pid:
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)


async def test_polars_submission_via_async_job(tmp_path):
    async with application(tmp_path) as app:
        response = await app.run_job("submit", task="sales", output=str(tmp_path / "sales.parquet"))
        assert response.success, response.answer
        run_id = response.answer["run_id"]
        response = await app.run_job("wait", run_id=run_id)
        record = response.answer
        assert record["state"] == "succeeded", record
        assert record["result"]["revenue"] == 75
        assert record["result"]["pid"] != os.getpid()
        assert [step["percentage"] for step in record["task_steps"]] == [100, 100, 100]
        assert Path(record["result"]["output"]).exists()
        assert not hasattr(app, "submit")


async def test_lazy_steps_failure_and_history(tmp_path):
    async with application(tmp_path) as app:
        manager = app.get_component("task_manager")
        ok = await manager.submit("probe")
        record = await manager.wait(ok)
        assert record.result["value"] == 2
        assert [step.percentage for step in record.task_steps] == [100, 100]
        bad = await manager.submit("probe", {"fail": True})
        record = await manager.wait(bad)
        assert record.state == "failed"
        assert len(record.task_steps) == 1
        assert record.task_steps[0].percentage is None
        assert "intentional failure" in record.error
        assert "Traceback" in await manager.logs(bad)
    async with application(tmp_path) as app:
        assert (await app.get_component("task_manager").status(ok)).state == "succeeded"


async def test_progress_job_updates_running_task_step(tmp_path):
    async with application(tmp_path) as app:
        manager = app.get_component("task_manager")
        run_id = await manager.submit("probe", {"delay": 30})
        running = await started(manager, run_id)

        response = await app.run_job(
            "report_task_progress",
            run_id=run_id,
            step_index=0,
            task_step={"name": running.task_steps[0].name, "percentage": 25},
        )

        assert response.success
        assert response.answer == {"run_id": run_id, "step_index": 0}
        assert (await manager.status(run_id)).task_steps[0].percentage == 25
        await manager.cancel(run_id)


async def test_queue_cancel_and_observer_timeout(tmp_path):
    async with application(tmp_path) as app:
        manager = app.get_component("task_manager")
        active = await manager.submit("probe", {"delay": 30})
        running = await started(manager, active)
        queued = await manager.submit("probe", {"marker": str(tmp_path / "never")})
        with pytest.raises(TimeoutError):
            await manager.wait(active, timeout=0.01)
        assert (await manager.status(active)).state == "running"
        assert (await manager.cancel(queued)).state == "cancelled"
        assert not (tmp_path / "never").exists()
        assert (await manager.cancel(active)).state == "cancelled"
        assert_dead(running.pid)


async def test_kill_and_shutdown(tmp_path):
    app = application(tmp_path)
    await app.start()
    manager = app.get_component("task_manager")
    first = await manager.submit("probe", {"delay": 30})
    record = await started(manager, first)
    killed = await manager.kill(first)
    assert killed.state == "cancelled"
    assert_dead(record.pid)
    second = await manager.submit("probe", {"delay": 30})
    record = await started(manager, second)
    await app.close()
    assert_dead(record.pid)
    assert (await manager.status(second)).state == "cancelled"
    with pytest.raises(RuntimeError):
        await manager.submit("probe")


async def test_cancel_immediately_and_escalate(tmp_path):
    async with application(tmp_path) as app:
        manager = app.get_component("task_manager")
        queued = await manager.submit("probe")
        killed = await manager.kill(queued)
        assert killed.state == "cancelled"
        manager.cancel_timeout = 10
        run_id = await manager.submit("probe", {"delay": 30})
        record = await started(manager, run_id)
        cancel = asyncio.create_task(manager.cancel(run_id))
        await asyncio.sleep(0.03)
        async with asyncio.timeout(3):
            killed = await manager.kill(run_id)
            assert killed.state == "cancelled"
            await cancel
        assert_dead(record.pid)


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


def test_async_step_rejects_sync_and_task_no_components():
    with pytest.raises(TypeError):

        class Invalid(BaseStep):
            def execute(self):
                pass

    assert not hasattr(ProbeTask({}), "app_context")


def test_plugin_manifest_config():
    manifest = parse_plugin_manifest("backends: {}\nconfig:\n  jobs: {}\n", plugin_name="test")
    assert isinstance(manifest, PluginManifest)
    assert manifest.config == {"jobs": {}}
    with pytest.raises(ValueError, match="application_defaults"):
        parse_plugin_manifest("application_defaults: {}\n", plugin_name="test")


@pytest.mark.parametrize(
    "text",
    [
        "backends: []\n",
        "config: []\n",
        "backends:\n  '': package.module:Backend\n",
        "backends:\n  backend: ''\n",
        "backends:\n  backend: 1\n",
    ],
)
def test_plugin_manifest_rejects_invalid_schema(text):
    with pytest.raises(ValueError, match="Plugin 'test' manifest is invalid"):
        parse_plugin_manifest(text, plugin_name="test")


def test_plugin_manifest_defaults_and_normalizes_backend_strings():
    manifest = parse_plugin_manifest(
        "backends:\n  ' sales ': ' package.module:Backend '\n",
        plugin_name="test",
    )

    assert manifest.backends == {"sales": "package.module:Backend"}
    assert manifest.config == {}


def test_plugin_rejects_object_entry_point_targets():
    entry = EntryPoint(name="old", value="package.module:create_plugin", group="axonx.plugins")

    with pytest.raises(ValueError, match="must target a package containing plugin.yaml"):
        _load_plugin("old", entry)


def test_http_client_discovers_service_from_environment(monkeypatch, capsys):
    from axonx.components.client import HttpClient

    monkeypatch.setenv(AXONX_SERVICE_INFO, '{"host": "service.internal", "port": 4321}')
    assert HttpClient().url == "http://service.internal:4321"
    assert HttpClient(url="https://explicit.example/").url == "https://explicit.example"

    monkeypatch.setenv(AXONX_SERVICE_INFO, '{"host": "missing-port"}')
    assert HttpClient().url == AXONX_DEFAULT_URL
    assert f"Invalid {AXONX_SERVICE_INFO} value" in capsys.readouterr().err


async def test_http_service_publishes_service_info(monkeypatch):
    import json
    from axonx.components.service import HttpService

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


async def test_http_and_mcp_expose_the_same_jobs():
    import httpx
    from fastmcp import Client
    from axonx.components.service import HttpService

    app = Application(
        jobs={
            "visible": {
                "description": "A visible job",
                "parameters": {
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                },
            },
            "hidden": {"enable_serve": False},
            "scheduled": {"backend": "interval", "interval": 60},
        },
    )
    service = HttpService()
    server = service.build_service(app)

    async with server.router.lifespan_context(server):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=server),
            base_url="http://test",
        ) as http_client:
            response = await http_client.get("/jobs")
            assert response.status_code == 200
            assert [job["name"] for job in response.json()] == ["visible"]
            assert response.json()[0]["inputSchema"]["properties"] == {
                "value": {"type": "string"},
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
            assert source == "https://service.example/mcp"
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

    async with McpClient(url="https://service.example") as client:
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
        jobs={
            "demo": {
                "steps": [
                    {"backend": "version_step"},
                    {"backend": "demo_step"},
                ],
            },
        },
    )
    async with app:
        results = await asyncio.gather(*(app.run_job("demo") for _ in range(5)))
        assert all(r.answer.startswith("Demo running on AxonX ") for r in results)
        assert all(r.answer.endswith(r.metadata["version"]) for r in results)
        assert len({id(r) for r in results}) == 5


async def test_submit_invalid_and_status_snapshot(tmp_path):
    async with application(tmp_path) as app:
        manager = app.get_component("task_manager")
        with pytest.raises(ValueError):
            await manager.submit("missing")
        with pytest.raises(ValueError):
            await manager.submit("probe", {"unknown": 1})
        run_id = await manager.submit("probe")
        record = await manager.wait(run_id)
        record.result["value"] = -1
        assert (await manager.status(run_id)).result["value"] == 2
        with pytest.raises(KeyError):
            await manager.logs("../../outside")


async def test_fifo_and_distinct_processes(tmp_path):
    async with application(tmp_path) as app:
        manager = app.get_component("task_manager")
        ids = [await manager.submit("probe", {"delay": 0.05}) for _ in range(3)]
        records = await asyncio.gather(*(manager.wait(key) for key in ids))
        assert len({r.pid for r in records}) == 3
        assert all(a.finished_at <= b.started_at for a, b in zip(records, records[1:]))


async def test_unfinished_history_marked_lost(tmp_path):
    import json

    directory = tmp_path / "tasks" / "default" / "old"
    directory.mkdir(parents=True)
    (directory / "run.json").write_text(
        json.dumps({"id": "old", "task": "probe", "created_at": 1, "state": "running", "pid": os.getpid()}),
    )
    async with application(tmp_path) as app:
        record = await app.get_component("task_manager").status("old")
        assert record.state == "lost"
        assert record.pid == os.getpid()  # recovered PIDs are never signalled
