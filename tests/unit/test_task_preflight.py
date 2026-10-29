"""Check same-name startup decisions and actionable local and remote recovery hints."""

import json
import shlex
from unittest.mock import Mock

import psutil
import pytest
from loguru import logger

from axonx.task.builtins.demo import DemoTask
from axonx.task.core.base import BaseTask
from axonx.task.models.identity import TaskState
from axonx.task.models.params import BaseOutputParams
from axonx.task.runtime import lifecycle
from axonx.task.runtime.executor import TaskExecutor
from axonx.task.runtime.settings import ExecutionSettings, normalize_execution_target
from axonx.task.storage.workspace import read_task_metadata, task_path, write_task_metadata
from axonx.utils.logging import LoggingConfig, configure_logging


@pytest.fixture
def task(tmp_path):
    configure_logging(LoggingConfig(log_to_console=False, log_to_file=False))
    original = DemoTask({"task_name": "same", "x": 1, "y": 2}, workspace_path=tmp_path, reg_name="demo")
    status = TaskExecutor().execute(original)
    return original, status, original.task_dir


def running(status, directory, **changes):
    status = status.model_copy(update={"state": TaskState.RUNNING, "finished_at": None, **changes})
    write_task_metadata(directory, status)
    return status


def restart(original, *, execution_target=None):
    return TaskExecutor().execute(
        DemoTask(
            {"task_name": "same", "x": 10, "y": 20},
            workspace_path=original.workspace_path,
            reg_name="demo",
            execution_target=execution_target,
        )
    )


def test_confirmed_local_conflict_gives_an_explicit_local_kill_command(task):
    original, status, directory = task
    running(status, directory)
    before = (directory / "metadata.json").read_bytes()
    with pytest.raises(FileExistsError, match="Task is running:") as error:
        restart(original)
    command = shlex.join(
        ["axonx", "kill", "--task-id", status.task_id, "--workspace-dir", str(original.workspace_path)]
    )
    assert command in str(error.value)
    assert "--target" not in str(error.value)
    assert (directory / "metadata.json").read_bytes() == before


def test_unknown_local_process_blocks_startup_but_observation_remains_available(task, monkeypatch):
    original, status, directory = task
    running(status, directory)
    before = (directory / "metadata.json").read_bytes()
    monkeypatch.setattr(lifecycle, "process_instance", Mock(side_effect=psutil.AccessDenied(status.pid)))
    with pytest.raises(FileExistsError, match="cannot verify the local process") as error:
        restart(original)
    assert "Task is running:" not in str(error.value)
    assert lifecycle.reconcile_task(directory, status.started_at).state == TaskState.RUNNING
    assert (directory / "metadata.json").read_bytes() == before


def test_local_dead_process_logs_repair_before_overwrite(task, monkeypatch):
    original, status, directory = task
    running(status, directory)
    persistent = directory / "persistent"
    persistent.mkdir(exist_ok=True)
    (persistent / "history.txt").write_text("keep")
    monkeypatch.setattr(lifecycle, "process_instance", lambda *_: None)
    messages = []
    sink = logger.add(lambda message: messages.append(message.record["message"]))
    try:
        result = restart(original)
    finally:
        logger.remove(sink)
    repair = next(i for i, text in enumerate(messages) if "Reconciled stale Task" in text)
    overwrite = next(i for i, text in enumerate(messages) if "Overwrite task_id=" in text)
    assert repair < overwrite
    assert "state=running->failed" in messages[repair]
    assert "state=failed" in messages[overwrite]
    assert result.output_params["result"] == 30
    assert (persistent / "history.txt").read_text() == "keep"


@pytest.mark.parametrize("target", [None, "https://10.0.0.8:1024"])
def test_foreign_running_task_is_unchanged_and_uses_the_execution_machine_path(task, monkeypatch, target):
    original, status, directory = task
    running(status, directory, machine_id="foreign", execution_target=target, workspace_dir="/source/shared workspace")
    before = (directory / "metadata.json").read_bytes()
    monkeypatch.setattr(lifecycle, "process_instance", lambda *_: pytest.fail("Probed a foreign process"))
    with pytest.raises(FileExistsError, match="another machine") as error:
        restart(original)
    expected = shlex.join(
        [
            "axonx",
            "kill",
            "--task-id",
            status.task_id,
            "--target",
            target or "<HOST:PORT>",
            "--workspace-dir",
            "/source/shared workspace",
        ]
    )
    assert expected in str(error.value)
    assert "cannot be verified or repaired here" in str(error.value)
    assert (directory / "metadata.json").read_bytes() == before


def test_foreign_terminal_record_can_be_overwritten(task, monkeypatch):
    original, status, directory = task
    status.machine_id = "foreign"
    write_task_metadata(directory, status)
    monkeypatch.setattr(lifecycle, "process_instance", lambda *_: pytest.fail("Probed a terminal process"))
    assert restart(original).state == TaskState.SUCCEEDED


def test_orphan_running_child_does_not_route_kill_to_an_already_finished_parent(task, monkeypatch):
    original, parent, _ = task
    child = TaskExecutor().execute(
        DemoTask({"task_name": "child", "x": 1, "y": 2}, workspace_path=original.workspace_path, reg_name="demo")
    )
    child.parent_task_id = parent.task_id
    child = running(child, task_path(original.workspace_path, child.task_id))
    assert lifecycle.execution_owner(original.workspace_path, child).task_id == child.task_id
    monkeypatch.setattr(lifecycle, "process_instance", lambda *_: None)
    assert lifecycle.kill_task(original.workspace_path, child.task_id).state == TaskState.FAILED


@pytest.mark.parametrize("problem", ["missing", "json", "encoding", "schema", "identity", "symlink"])
def test_invalid_metadata_is_reported_without_replacing_any_task_files(task, problem):
    original, status, directory = task
    path = directory / "metadata.json"
    marker = directory / "output.txt"
    marker.write_text("keep")
    if problem == "missing":
        path.unlink()
    elif problem == "json":
        path.write_text("{")
    elif problem == "encoding":
        path.write_bytes(b"\xff")
    elif problem == "schema":
        path.write_text(json.dumps({"task_id": status.task_id}))
    elif problem == "identity":
        write_task_metadata(directory, status.model_copy(update={"task_id": "base#demo#other"}))
    else:
        external = directory.parent / "external.json"
        external.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(external)
    before = path.read_bytes() if path.exists() else None
    with pytest.raises((FileNotFoundError, ValueError)) as error:
        restart(original)
    assert "metadata" in str(error.value)
    assert "not overwritten" in str(error.value)
    assert (path.read_bytes() if path.exists() else None) == before
    assert marker.read_text() == "keep"
    assert read_task_metadata(directory, status.task_id) is None


def test_execution_location_reaches_nested_tasks_and_root_conflict_hints(tmp_path):
    configure_logging(LoggingConfig(log_to_console=False, log_to_file=False))

    class Parent(BaseTask):
        def build_task_steps(self):
            yield lambda: self.run_task("demo", x=1, y=2)

        def build_output_params(self):
            return BaseOutputParams()

    executor = TaskExecutor(resolve_task=lambda _: DemoTask)
    parent = executor.execute(
        Parent({"task_name": "same"}, workspace_path=tmp_path, reg_name="parent", execution_target="10.0.0.8:1024")
    )
    child = read_task_metadata(task_path(tmp_path, parent.children[0].child_task_id), parent.children[0].child_task_id)
    assert parent.execution_target == child.execution_target == "http://10.0.0.8:1024"
    assert parent.workspace_dir == child.workspace_dir == str(tmp_path.resolve())
    parent = running(parent, task_path(tmp_path, parent.task_id), machine_id="foreign")
    child = running(child, task_path(tmp_path, child.task_id), machine_id="foreign")
    message = lifecycle.conflict_message(tmp_path, child)
    assert shlex.join(["axonx", "kill", "--task-id", parent.task_id]) in message
    assert "--target http://10.0.0.8:1024" in message


def test_advertised_target_is_explicit_and_independent_of_connection_defaults(monkeypatch):
    monkeypatch.setenv("AXONX_SERVICE_TARGET", "http://127.0.0.1:1024")
    settings = ExecutionSettings(execution_target="10.0.0.8:1024")
    assert settings.execution_target == "http://10.0.0.8:1024"
    assert ExecutionSettings().execution_target is None


@pytest.mark.parametrize(
    "value",
    [
        "127.0.0.1:1024",
        "0.0.0.0:1024",
        "[::1]:1024",
        "[::ffff:127.0.0.1]:1024",
        "worker.localhost:1024",
        "[::]:1024",
        "localhost:1024",
        "10.0.0.8",
        "http://worker.example:1024/jobs",
        "https://user:secret@worker.example:1024",
        "",
        "worker:99999",
    ],
)
def test_invalid_execution_address_is_rejected_before_any_files_are_replaced(task, value):
    original, _, directory = task
    before = (directory / "metadata.json").read_bytes()
    with pytest.raises(ValueError, match="execution_target"):
        restart(original, execution_target=value)
    assert (directory / "metadata.json").read_bytes() == before


def test_ipv6_execution_target_keeps_its_explicit_port():
    assert normalize_execution_target("[2001:db8::1]:1024") == "http://[2001:db8::1]:1024"
