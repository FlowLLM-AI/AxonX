"""Verify the HTTP surface with Task observation and an injected update backend."""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from time import monotonic, sleep

import pytest
from fastapi.testclient import TestClient

from axonx.app.components.sync.archive import build_archive
from axonx.app.components.sync.replica import prepare_replica
from axonx.app.config.models import ComponentConfig
from axonx.app.config.resolver import resolve_app_config
from axonx.app.core.application import Application
from axonx.client.config import PROTOCOL_FILE_NAME_HEADER
from axonx.task.builtins.demo import DemoTask
from axonx.task.models.identity import TaskState
from axonx.task.runtime.executor import TaskExecutor
from axonx.task.storage.logs import TaskLogReader
from axonx.task.storage.workspace import read_entry, task_path, write_task_metadata
from axonx.utils.logging import LoggingConfig, configure_logging


class UpdateOperations:
    def __init__(self):
        self.calls = []
        self.fail = False

    def prepare(self, mode):
        if self.fail:
            raise OSError("preparation failed")
        self.calls.append(("prepare", mode))
        return {"update_id": "a" * 32}

    def commit(self, update_id):
        self.calls.append(("commit", update_id))

    def status(self, update_id=None):
        return {"record": None, "log": "", "update_id": update_id}


@pytest.fixture
def application(tmp_path, monkeypatch):
    for name in ("SOCKET", "TOKEN", "DIRECTORY"):
        monkeypatch.delenv("AXONX_DAEMON_" + name, raising=False)
    config = resolve_app_config(log_config=False)
    config.update(workspace_dir=str(tmp_path), log_dir=str(tmp_path / "logs"), log_to_console=False, log_to_file=False)
    config["command"] = (sys.executable, "-u", "-m", "axonx.cli")
    config["environment"] = {}
    config["environment"]["PYTHONPATH"] = os.pathsep.join(
        filter(None, (str(Path(__file__).resolve().parents[2]), os.environ.get("PYTHONPATH")))
    )
    config["components"] = {
        key: value for key, value in config["components"].items() if key in {"task_index", "updater"}
    }
    config["components"]["task_index"]["default"]["poll_interval"] = 0.01
    config["service"] = {"backend": "http", "token": "test-token", "web_enabled": False}
    app = Application(updates=UpdateOperations(), **config)
    with TestClient(app.context.service.build_service(app), headers={"Authorization": "Bearer test-token"}) as client:
        yield app, client


def invoke(client, name, arguments):
    response = client.post(f"/jobs/{name}", json={"arguments": arguments})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["success"], payload
    return payload["answer"]


def test_config_job_returns_absolute_paths_and_excludes_runtime_callbacks(application):
    app, client = application
    app.app_config.components["cron"] = {
        "default": ComponentConfig(
            backend="cron",
            source="research",
            launch=lambda _: None,
            validate_command=lambda _: None,
        )
    }
    config = invoke(client, "get_config", {})
    assert config["workspace_dir"] == str(app.workspace.root)
    assert Path(config["log_dir"]).is_absolute()
    assert config["components"]["cron"]["default"] == {"backend": "cron", "source": "research"}
    assert config["service"]["token"] == "test-token"
    assert (
        client.post("/jobs/get_config", json={"arguments": {}}, headers={"Authorization": "Bearer wrong"}).status_code
        == 401
    )


@pytest.mark.asyncio
async def test_application_can_run_without_product_adapters(tmp_path):
    app = Application(workspace_dir=str(tmp_path), log_to_console=False, log_to_file=False)
    async with app:
        assert app.is_started
        assert not app.context.components
        assert not app.context.jobs
    assert not app.is_started


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["en", "zh"])
async def test_default_application_starts_with_packaged_agent_guides(tmp_path, language):
    config = resolve_app_config(log_config=False)
    config.update(
        workspace_dir=str(tmp_path),
        log_dir=str(tmp_path / "logs"),
        language=language,
        log_to_console=False,
        log_to_file=False,
    )
    app = Application(**config)
    async with app:
        agent = app.context.components["agent"]["default"]
        assert agent.dev_guide
        assert "axonx.task.storage.files" in agent.dev_guide


def test_update_is_committed_after_the_response_boundary(application):
    app, client = application
    record = invoke(client, "restart_service", {})
    assert app.context.updates.calls == [("prepare", "restart"), ("commit", record["update_id"])]
    assert app.context.metadata["maintenance"]


def test_failed_update_preparation_releases_application_admission(application):
    app, client = application
    app.context.updates.fail = True
    result = client.post("/jobs/restart_service", json={"arguments": {}}).json()
    assert not result["success"]
    assert not app.context.metadata.get("maintenance")
    app.context.updates.fail = False
    invoke(client, "restart_service", {})


def test_cli_execution_and_task_observation_share_the_workspace(application):
    app, client = application
    result = invoke(
        client,
        "cli",
        {
            "argv": [
                "exec",
                "--task",
                "demo",
                "--task-name",
                "http",
                "--workspace-dir",
                str(app.workspace.root),
                "--log-dir",
                str(app.app_config.log_dir),
                "--x",
                "2",
                "--y",
                "3",
            ]
        },
    )
    assert result["exit_code"] == 0
    assert json.loads(result["stdout"])["result"] == 5
    status = invoke(client, "status", {"task_id": "base#demo#http"})
    assert status["output_params"]["result"] == 5
    assert read_entry(app.workspace.root, status["task_id"]).started_at == datetime.fromisoformat(status["started_at"])
    deadline = monotonic() + 2
    summaries = []
    while not summaries and monotonic() < deadline:
        summaries = invoke(client, "list_task_statuses", {})
        sleep(0.01)
    assert summaries[0]["task_id"] == status["task_id"]
    assert "output_params" not in summaries[0]
    context = invoke(client, "get_task_context", {"task_id": status["task_id"]})
    assert context["status"]["started_at"] == status["started_at"]
    assert context["graph"]["selected_id"] == status["task_id"]
    assert invoke(client, "wait_task", {"task_id": status["task_id"]})["state"] == "succeeded"
    assert "run_id" not in status
    stale = (datetime.fromisoformat(status["started_at"]) - timedelta(seconds=1)).isoformat()
    rejected = client.post(
        "/jobs/read_task_log", json={"arguments": {"task_id": status["task_id"], "started_at": stale}}
    ).json()
    assert not rejected["success"]
    assert "restarted" in rejected["answer"]
    log = invoke(client, "read_task_log", {"task_id": status["task_id"], "started_at": status["started_at"]})
    assert "Task completed" in log["content"]
    events = client.post("/jobs/stream_task/events", json={"arguments": {"task_id": status["task_id"]}})
    assert events.status_code == 200
    assert '"kind": "result"' in events.text


def test_catalog_adapter_does_not_load_unrelated_plugin_tasks(application):
    app, client = application
    app.app_config.command = ()
    definition = invoke(client, "get_task_def", {"task": "demo"})
    assert definition["name"] == "demo"
    assert {"x", "y"} <= definition["input_schema"]["properties"].keys()


@pytest.mark.parametrize("arguments", [{}, {"include_schemas": False}, {"include_schemas": True}])
def test_task_definition_listing_runs_without_a_cli_command(application, monkeypatch, arguments):
    from axonx.plugin import catalog

    app, client = application
    app.app_config.command = ()
    monkeypatch.setattr(catalog, "list_installed_plugins", lambda: [])
    definitions = invoke(client, "list_task_defs", arguments)
    demo = next(item for item in definitions if item["name"] == "demo")
    assert demo["source"] == "native"
    assert ("input_schema" in demo) is arguments.get("include_schemas", True)
    assert ("output_schema" in demo) is arguments.get("include_schemas", True)


def test_upload_preview_and_workspace_deletion(application):
    app, client = application
    response = client.post("/upload", content=b"hello", headers={PROTOCOL_FILE_NAME_HEADER: "example.txt"})
    assert response.status_code == 200, response.text
    staged = response.json()["answer"]
    assert Path(staged["location"]).read_bytes() == b"hello"
    assert invoke(client, "preview_file", {"path": staged["path"]})["content"] == "hello"
    assert client.delete("/upload", params={"path": staged["path"]}).status_code == 200
    assert not Path(staged["location"]).exists()
    (app.workspace.root / ".internal").mkdir()
    listing = invoke(client, "list_entries", {})
    assert ".internal" in [entry["name"] for entry in listing["entries"]]
    assert invoke(client, "delete_entries", {"paths": [".internal"]})[0]["deleted"] == ".internal"
    assert not (app.workspace.root / ".internal").exists()
    (app.workspace.root / "example.txt").write_text("example")
    assert invoke(client, "delete_entries", {"paths": ["example.txt"]})[0]["deleted"] == "example.txt"


def test_workspace_deletion_has_no_task_lifecycle_policy(application):
    app, client = application
    status = TaskExecutor().execute(
        DemoTask({"task_name": "delete", "x": 1, "y": 2}, workspace_path=app.workspace.root, reg_name="demo")
    )
    status.state = TaskState.RUNNING
    directory = task_path(app.workspace.root, status.task_id)
    write_task_metadata(directory, status)
    path = directory.relative_to(app.workspace.root).as_posix()
    assert invoke(client, "delete_entries", {"paths": [path]}) == [{"deleted": path, "kind": "directory"}]
    assert not directory.exists()


def test_sync_archive_round_trip_through_the_http_adapters(application, tmp_path):
    app, client = application
    assert "sync" not in app.context.components
    source = tmp_path / "source"
    configure_logging(LoggingConfig(log_to_console=False, log_to_file=False))
    status = TaskExecutor().execute(
        DemoTask({"task_name": "replica", "x": 3, "y": 4}, workspace_path=source, reg_name="demo")
    )
    plan = prepare_replica(source, status.task_id, tmp_path / "prepared", 1_000_000, TaskLogReader(tmp_path / "logs"))
    archive = tmp_path / "replica.tar.gz"
    build_archive({status.task_id: plan}, [status.task_id], archive)
    response = client.post("/upload", content=archive.read_bytes(), headers={PROTOCOL_FILE_NAME_HEADER: archive.name})
    assert response.status_code == 200, response.text
    staged = response.json()["answer"]
    applied = invoke(client, "sync_tasks", {"path": staged["path"]})
    assert applied["applied"] == [str(task_path(app.workspace.root, status.task_id).relative_to(app.workspace.root))]
    assert not Path(staged["location"]).exists()
    replica = invoke(client, "status", {"task_id": status.task_id})
    assert replica["replica"]["purpose"] == "display"
    assert replica["output_params"]["result"] == 7
    index = invoke(client, "task_sync_index", {})
    assert status.task_id in index["tasks"]
    deletion = invoke(client, "sync_tasks", {"deletions": applied["applied"]})
    assert deletion["deleted"] == applied["applied"]
    assert read_entry(app.workspace.root, status.task_id) is None


def test_explicit_execution_location_is_recorded_by_remote_cli(application):
    app, client = application
    result = invoke(
        client,
        "cli",
        {
            "argv": [
                "exec",
                "--task",
                "demo",
                "--task-name",
                "advertised",
                "--x",
                "1",
                "--y",
                "2",
                "--execution-target",
                "10.0.0.8:1024",
                "--workspace-dir",
                str(app.workspace.root),
                "--log-dir",
                str(app.app_config.log_dir),
            ]
        },
    )
    assert result["exit_code"] == 0
    status = invoke(client, "status", {"task_id": "base#demo#advertised"})
    assert status["execution_target"] == "http://10.0.0.8:1024"
    assert status["workspace_dir"] == str(app.workspace.root.resolve())
