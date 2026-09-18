"""Task runtime, plugin, worker, and service integration tests."""

# Several tests intentionally define invalid implementations or inspect internal behavior.
# pylint: disable=invalid-overridden-method,missing-class-docstring
# pylint: disable=missing-function-docstring,protected-access,unused-variable,wrong-import-order

import asyncio
import json
import os
import signal
from pathlib import Path

import pytest

from axonx import Application, BaseComponent, BaseInputParams, BaseTask
from axonx.components.registry import R
from axonx.config import resolve_app_config
from axonx.constants import (
    AXONX_DEFAULT_CONNECT_HOST,
    AXONX_DEFAULT_PORT,
    AXONX_SERVICE_INFO,
    AXONX_TASK_LOG_DIR,
    AXONX_TASK_TIMEZONE,
    AXONX_TASK_WORKSPACE_DIR,
)
from axonx.enums import TaskState, TaskType
from axonx.plugin.manifest import parse_plugin_manifest
from axonx.schema import PluginManifest, TaskStatus
from axonx.task.arguments import build_task_argv, split_task_arguments


def application(tmp_path, *, log_dir="logs", **manager):
    config = resolve_app_config(workspace_dir=str(tmp_path), log_dir=str(log_dir))
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
    monkeypatch.setattr(
        os,
        "killpg",
        lambda *_args: pytest.fail("manager close must not signal task processes"),
    )
    monkeypatch.setenv("AXONX_PARENT_ONLY", "not inherited")
    log_dir = tmp_path / "service-logs"
    monkeypatch.setenv(AXONX_SERVICE_INFO, '{"host":"service.internal","port":4321}')
    argv = ["--task", "demo", "--output", "result file.parquet"]
    async with application(tmp_path, log_dir=log_dir) as app:
        manager = app.get_component("task_manager")
        await manager.submit(argv)
        await asyncio.gather(*manager._supervisor.monitors)

    command, options = calls[0]
    assert command[1:] == ("-m", "axonx.cli", "exec", *argv)
    assert options["start_new_session"] is True
    assert "AXONX_PARENT_ONLY" not in options["env"]
    assert AXONX_SERVICE_INFO not in options["env"]
    assert options["env"][AXONX_TASK_WORKSPACE_DIR] == str(tmp_path.resolve())
    assert options["env"][AXONX_TASK_LOG_DIR] == str(log_dir.resolve())
    assert options["env"][AXONX_TASK_TIMEZONE] == "Asia/Shanghai"
    assert options["env"]["PYTHONPATH"] == str(Path(__file__).parent)
    assert options["stderr"] == asyncio.subprocess.PIPE
    success_log = capsys.readouterr().err
    assert "Task process 12345 (demo) completed successfully" in success_log


async def test_task_manager_terminates_and_reaps_workers_on_close(monkeypatch, tmp_path):
    signals = []

    class Process:
        pid = 34567
        returncode = None

        def __init__(self):
            self.stderr = asyncio.StreamReader()
            self.exited = asyncio.Event()

        async def wait(self):
            await self.exited.wait()
            return self.returncode

        def finish(self, returncode):
            self.returncode = returncode
            self.stderr.feed_eof()
            self.exited.set()

    process = Process()

    async def create_subprocess_exec(*_command, **_options):
        return process

    def killpg(pid, sig):
        signals.append((pid, sig))
        process.finish(-sig)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_subprocess_exec)
    monkeypatch.setattr(os, "killpg", killpg)
    app = application(tmp_path, terminate_grace_seconds=0.1)
    await app.start()
    manager = app.get_component("task_manager")
    await manager.submit(["--task", "running"])
    status = TaskStatus(task_id="analysis#analysis#running", task_type=TaskType.ANALYSIS, state=TaskState.RUNNING, pid=process.pid)
    (tmp_path / "analysis" / status.task_id).mkdir(parents=True)
    await manager._write_status(status)

    await app.close()

    assert signals == [(process.pid, signal.SIGTERM)]
    assert process.returncode == -signal.SIGTERM
    assert manager._supervisor.processes == {}
    assert manager._supervisor.monitors == set()
    status = await manager.get_status(status.task_id)
    assert status.state == TaskState.CANCELLED
    assert status.exit_code == 130


async def test_task_manager_kills_worker_after_shutdown_grace_period(monkeypatch, tmp_path):
    signals = []

    class Process:
        pid = 45678
        returncode = None

        def __init__(self):
            self.stderr = asyncio.StreamReader()
            self.exited = asyncio.Event()

        async def wait(self):
            await self.exited.wait()
            return self.returncode

    process = Process()

    async def create_subprocess_exec(*_command, **_options):
        return process

    def killpg(pid, sig):
        signals.append((pid, sig))
        if sig == signal.SIGKILL:
            process.returncode = -sig
            process.stderr.feed_eof()
            process.exited.set()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_subprocess_exec)
    monkeypatch.setattr(os, "killpg", killpg)
    app = application(tmp_path, terminate_grace_seconds=0)
    await app.start()
    manager = app.get_component("task_manager")
    await manager.submit(["--task", "stubborn"])

    await app.close()

    assert signals == [
        (process.pid, signal.SIGTERM),
        (process.pid, signal.SIGKILL),
    ]
    assert process.returncode == -signal.SIGKILL


def test_task_manager_rejects_negative_shutdown_grace_period(tmp_path):
    with pytest.raises(ValueError, match="terminate_grace_seconds"):
        application(tmp_path, terminate_grace_seconds=-1)


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
    class ProbeInputParams(BaseInputParams):
        pass

    class ProbeTask(BaseTask):
        task_type = TaskType.ANALYSIS
        input_cls = ProbeInputParams

        def build_task_steps(self):
            return ()

        def build_output_params(self):
            return self.output_cls()

    assert not hasattr(ProbeTask({}, workspace_path=".", reg_name="probe"), "app_context")


def test_plugin_manifest_accepts_tasks_and_declarative_jobs():
    manifest = parse_plugin_manifest(
        """
tasks:
  demo: package.module:Task
components:
  step:
    demo_step: package.module:DemoStep
jobs:
  run_demo:
    steps:
      - backend: submit_task
    defaults:
      task: demo
  nightly_demo:
    backend: cron
    cron: 0 2 * * *
    steps:
      - backend: submit_task
    defaults:
      task: demo
""",
        "test",
    )

    assert isinstance(manifest, PluginManifest)
    assert manifest.tasks == {"demo": "package.module:Task"}
    assert manifest.components == {"step": {"demo_step": "package.module:DemoStep"}}
    assert manifest.jobs["run_demo"].backend == "simple"
    assert manifest.jobs["nightly_demo"].backend == "cron"


def test_plugin_manifest_rejects_unknown_sections():
    with pytest.raises(ValueError, match="backends"):
        parse_plugin_manifest("backends: {}\n", "test")


@pytest.mark.parametrize(
    "text",
    [
        "tasks: []\n",
        "tasks:\n  '': package.module:Task\n",
        "tasks:\n  task: ''\n",
        "tasks:\n  task: 1\n",
        "jobs: []\n",
        "jobs:\n  demo: invalid\n",
        "components: []\n",
        "components:\n  step: []\n",
    ],
)
def test_plugin_manifest_rejects_invalid_schema(text):
    with pytest.raises(ValueError, match="Plugin 'test' manifest is invalid"):
        parse_plugin_manifest(text, "test")


def test_plugin_manifest_defaults_and_normalizes_task_strings():
    manifest = parse_plugin_manifest("tasks:\n  ' example ': ' package.module:Task '\n", "test")

    assert manifest.tasks == {"example": "package.module:Task"}


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
    from axonx.components.service import HttpService

    previous = '{"host": "previous", "port": 1234}'
    monkeypatch.setenv(AXONX_SERVICE_INFO, previous)
    app = Application(app_name="Configured AxonX")
    service = HttpService(host="127.0.0.2", port=4321)
    server = service.build_service(app)

    assert server.title == "Configured AxonX"
    async with server.router.lifespan_context(server):
        assert json.loads(os.environ[AXONX_SERVICE_INFO]) == {
            "host": "127.0.0.2",
            "port": 4321,
        }
        assert app.is_started

    assert os.environ[AXONX_SERVICE_INFO] == previous
    assert not app.is_started


async def test_http_service_advertises_loopback_for_default_wildcard_bind(
    monkeypatch,
):
    from axonx.components.service import HttpService

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


async def test_http_service_serves_studio_spa_and_cors(tmp_path):
    import httpx

    from axonx.components.service import HttpService

    static_dir = tmp_path / "studio"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<main>AxonX Studio</main>", encoding="utf-8")
    server = HttpService(web_static_dir=str(static_dir)).build_service(Application())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server), base_url="http://test") as client:
        page = await client.get("/tasks")
        preflight = await client.options(
            "/jobs",
            headers={
                "origin": "http://127.0.0.1:4173",
                "access-control-request-method": "GET",
            },
        )

    assert page.text == "<main>AxonX Studio</main>"
    assert page.headers["cache-control"] == "no-cache, no-store, must-revalidate"
    assert preflight.headers["access-control-allow-origin"] == "*"


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


async def test_status_job_returns_failure_for_unknown_task_without_logging_traceback(tmp_path, capsys):
    async with application(tmp_path) as app:
        response = await app.run_job("status", task_id="etl#missing")

    assert response.success is False
    assert response.answer == "Task not found: etl#missing"
    assert "Traceback" not in capsys.readouterr().err


def test_structured_task_submission_is_encoded_losslessly():
    task, config = split_task_arguments(
        {
            "task": "sample",
            "start_date": "00100101",
            "dry_run": True,
            "options": {"markets": ["CN", "HK"]},
        },
    )

    assert build_task_argv(task, config) == [
        "--task",
        "sample",
        "--start-date",
        '"00100101"',
        "--dry-run",
        "true",
        "--options",
        '{"markets":["CN","HK"]}',
    ]


@pytest.mark.parametrize("key", ["foo-bar", "foo.bar", "_hidden"])
def test_structured_task_submission_rejects_non_roundtrippable_keys(key):
    with pytest.raises(ValueError, match="Invalid Task configuration key"):
        build_task_argv("sample", {key: 1})


async def test_structured_task_submission_validates_before_launch(monkeypatch, tmp_path):
    calls = []

    async def submit(argv):
        calls.append(argv)

    async with application(tmp_path) as app:
        manager = app.get_component("task_manager")
        monkeypatch.setattr(manager, "submit", submit)

        invalid = await app.run_job("submit", task="demo", x="not-an-integer", y=2)

    assert invalid.success is False
    assert "validation error" in invalid.answer
    assert not calls


async def test_task_listing_jobs_separate_runtime_and_installed_tasks(tmp_path):
    async with application(tmp_path) as app:
        runtime = await app.run_job("list_task_ids")
        installed = await app.run_job("list_installed_task_definitions")

    assert runtime.answer == []
    tasks = {info["name"]: info for info in installed.answer}
    assert "download_tushare_task" in tasks
    assert tasks["download_tushare_task"]["source"] == "native"
    assert tasks["download_tushare_task"]["plugin"] is None
    assert set(tasks["download_tushare_task"]["input_schema"]["properties"]) == {
        "task_name",
        "include_time",
        "source_tasks",
        "start_date",
        "end_date",
        "days_back",
        "timeout",
        "datasets",
    }


async def test_http_service_installs_task_plugin_wheel(monkeypatch, tmp_path):
    import httpx

    from axonx.components.service import HttpService
    from axonx.plugin import build_wheel, inspect_wheel, source_sha256

    source = Path("plugins/alpha158").resolve()
    wheel = build_wheel(source, tmp_path / "build" / source_sha256(source))
    artifact = inspect_wheel(wheel)
    app = Application(
        workspace_dir=str(tmp_path / "workspace"),
        components={
            "plugin": {
                "default": {
                    "backend": "local",
                    "allow_remote_install": True,
                    "install_token": "secret",
                },
            },
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
    assert response.json()["tasks"] == {
        "a158_etl": "axonx_alpha158.etl:Alpha158Task",
        "a158_factor": "axonx_alpha158.analysis:FactorAnalysisTask",
        "a158_train": "axonx_alpha158.train:LgbmTrainTask",
        "a158_predict": "axonx_alpha158.predict:LgbmPredictTask",
    }
    assert response.json()["components"] == {}
    assert response.json()["jobs"] == {}
    assert response.json()["restart_required"] is False
    assert plugins.json()["answer"][0]["wheel_sha256"] == artifact.sha256
