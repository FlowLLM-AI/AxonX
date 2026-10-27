"""Verify task replacement, observation and replication without a second task key."""

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from axonx.app.components.sync.applier import TaskArchiveApplier
from axonx.app.components.sync.archive import build_archive
from axonx.app.components.sync.errors import SnapshotChangedError
from axonx.app.components.sync.replica import prepare_group, task_group
from axonx.app.components.task_index.stream import TaskEventStream
from axonx.app.steps.task.query import WaitTaskStep
from axonx.task.builtins.demo import DemoTask
from axonx.task.core.base import BaseTask
from axonx.task.models.identity import TaskState
from axonx.task.models.params import BaseOutputParams
from axonx.task.runtime import lifecycle
from axonx.task.runtime.executor import TaskExecutor
from axonx.task.storage.logs import TaskLogReader
from axonx.task.storage.workspace import read_entry, scan_metadata, task_path, write_task_metadata
from axonx.utils.logging import LoggingConfig, configure_logging, get_logger


@pytest.fixture
def executor(tmp_path):
    configure_logging(LoggingConfig(log_to_console=False, log_to_file=False))
    return TaskExecutor()


def test_rerun_replaces_current_outputs_and_preserves_only_explicit_history(executor, tmp_path):
    first = executor.execute(DemoTask({"task_name": "same", "x": 1, "y": 2}, workspace_path=tmp_path, reg_name="demo"))
    directory = task_path(tmp_path, first.task_id)
    (directory / "old-output.txt").write_text("old")
    persistent = directory / "persistent"
    persistent.mkdir()
    (persistent / "history.txt").write_text("retained")
    second = executor.execute(
        DemoTask({"task_name": "same", "x": 10, "y": 20}, workspace_path=tmp_path, reg_name="demo")
    )
    assert first.task_id == second.task_id
    assert second.started_at > first.started_at
    assert read_entry(tmp_path, first.task_id).output_params["result"] == 30
    assert not (directory / "old-output.txt").exists()
    assert (persistent / "history.txt").read_text() == "retained"
    assert len(list(directory.parent.iterdir())) == 1
    assert "run_id" not in second.model_dump()
    assert {path.name for path in tmp_path.iterdir()} == {"base"}


def test_same_name_cannot_replace_a_running_task(tmp_path):
    configure_logging(LoggingConfig(log_to_console=False, log_to_file=False))

    class ConflictTask(DemoTask):
        def initialize(self):
            before = self.metadata_path.read_bytes()
            with pytest.raises(FileExistsError, match="Task is running"):
                TaskExecutor().execute(
                    DemoTask(self.input_params.model_dump(), workspace_path=tmp_path, reg_name="demo")
                )
            assert self.metadata_path.read_bytes() == before
            super().initialize()

    result = TaskExecutor().execute(
        ConflictTask({"task_name": "same", "x": 1, "y": 2}, workspace_path=tmp_path, reg_name="demo")
    )
    assert result.state == TaskState.SUCCEEDED


def test_rerun_start_time_stays_distinct_when_the_clock_moves_back(executor, tmp_path, monkeypatch):
    first = executor.execute(DemoTask({"task_name": "same", "x": 1, "y": 2}, workspace_path=tmp_path, reg_name="demo"))

    class EarlierClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return (first.started_at - timedelta(seconds=1)).astimezone(tz or UTC)

    monkeypatch.setattr("axonx.task.runtime.executor.datetime", EarlierClock)
    second = executor.execute(DemoTask({"task_name": "same", "x": 3, "y": 4}, workspace_path=tmp_path, reg_name="demo"))
    assert second.started_at > first.started_at
    assert read_entry(tmp_path, second.task_id).started_at == second.started_at


def test_metadata_scans_leave_dead_local_tasks_unchanged(executor, tmp_path):
    status = executor.execute(
        DemoTask({"task_name": "observe", "x": 1, "y": 2}, workspace_path=tmp_path, reg_name="demo")
    )
    status.state = TaskState.RUNNING
    status.pid = 2_147_483_647
    status.finished_at = None
    directory = task_path(tmp_path, status.task_id)
    write_task_metadata(directory, status)
    before = {path: path.read_bytes() for path in directory.iterdir() if path.is_file()}
    entries, versions = scan_metadata(tmp_path, {}, {})
    assert entries[status.task_id].state == TaskState.RUNNING
    cached, unchanged_versions = scan_metadata(tmp_path, entries, versions)
    assert cached[status.task_id] is entries[status.task_id]
    assert unchanged_versions == versions
    assert {path: path.read_bytes() for path in directory.iterdir() if path.is_file()} == before
    assert {path.name for path in tmp_path.iterdir()} == {"base"}


def test_explicit_reconciliation_keeps_a_newer_execution_unchanged(executor, tmp_path, monkeypatch):
    first = executor.execute(DemoTask({"task_name": "same", "x": 1, "y": 2}, workspace_path=tmp_path, reg_name="demo"))
    second = executor.execute(DemoTask({"task_name": "same", "x": 3, "y": 4}, workspace_path=tmp_path, reg_name="demo"))
    second.state = TaskState.RUNNING
    directory = task_path(tmp_path, second.task_id)
    write_task_metadata(directory, second)
    monkeypatch.setattr(lifecycle, "process_instance", lambda *_: None)
    assert lifecycle.reconcile_task(directory, first.started_at).state == TaskState.RUNNING
    assert lifecycle.reconcile_task(directory, second.started_at).state == TaskState.FAILED


def test_kill_refuses_a_restart_during_termination(executor, tmp_path, monkeypatch):
    current = executor.execute(
        DemoTask({"task_name": "same", "x": 1, "y": 2}, workspace_path=tmp_path, reg_name="demo")
    )
    current.state = TaskState.RUNNING
    directory = task_path(tmp_path, current.task_id)
    write_task_metadata(directory, current)
    replacement = current.model_copy(update={"started_at": current.started_at + timedelta(seconds=1)})
    monkeypatch.setattr(lifecycle, "process_instance", lambda *_: None)
    monkeypatch.setattr(lifecycle, "wait_processes", lambda *_: write_task_metadata(directory, replacement))
    with pytest.raises(ValueError, match="restarted before termination"):
        lifecycle.kill_task(tmp_path, current.task_id)
    assert read_entry(tmp_path, current.task_id).started_at == replacement.started_at
    assert read_entry(tmp_path, current.task_id).state == TaskState.RUNNING


def test_killing_a_finished_child_cannot_stop_a_restarted_parent(executor, tmp_path, monkeypatch):
    parent = executor.execute(
        DemoTask({"task_name": "parent", "x": 1, "y": 2}, workspace_path=tmp_path, reg_name="demo")
    )
    child = executor.execute(DemoTask({"task_name": "child", "x": 3, "y": 4}, workspace_path=tmp_path, reg_name="demo"))
    child.parent_task_id = parent.task_id
    write_task_metadata(task_path(tmp_path, child.task_id), child)
    replacement = parent.model_copy(
        update={"state": TaskState.RUNNING, "started_at": child.started_at + timedelta(seconds=1)}
    )
    write_task_metadata(task_path(tmp_path, parent.task_id), replacement)
    monkeypatch.setattr(lifecycle, "signal_process", lambda *_args, **_kwargs: pytest.fail("Signalled the new parent"))
    assert lifecycle.execution_owner(tmp_path, child).task_id == child.task_id
    assert lifecycle.kill_task(tmp_path, child.task_id).state == TaskState.SUCCEEDED
    assert read_entry(tmp_path, parent.task_id).state == TaskState.RUNNING


def test_cli_kill_uses_only_the_task_id(tmp_path):
    code = """
import sys, time
from axonx.utils.logging import LoggingConfig, configure_logging
from axonx.task.builtins.demo import DemoTask
from axonx.task.runtime.executor import TaskExecutor
class WaitingTask(DemoTask):
    def initialize(self):
        print('ready', flush=True)
        time.sleep(30)
configure_logging(LoggingConfig(log_to_console=False, log_to_file=False))
task = WaitingTask({'task_name': 'kill', 'x': 1, 'y': 2}, workspace_path=sys.argv[1], reg_name='demo')
TaskExecutor().execute(task)
"""
    with subprocess.Popen([sys.executable, "-c", code, str(tmp_path)], stdout=subprocess.PIPE, text=True) as child:
        try:
            assert child.stdout.readline().strip() == "ready"
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "axonx.cli",
                    "kill",
                    "--task-id",
                    "base#demo#kill",
                    "--workspace-dir",
                    str(tmp_path),
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            assert result.returncode == 0, result.stderr
            assert read_entry(tmp_path, "base#demo#kill").state == TaskState.FAILED
            child.wait(timeout=5)
        finally:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=5)


@pytest.mark.asyncio
async def test_wait_and_stream_refuse_to_follow_a_restart(executor, tmp_path):
    first = executor.execute(DemoTask({"task_name": "same", "x": 1, "y": 2}, workspace_path=tmp_path, reg_name="demo"))
    first.state = TaskState.RUNNING
    replacement = first.model_copy(update={"started_at": first.started_at + timedelta(seconds=1)})
    read = AsyncMock(side_effect=[first, replacement])
    step = SimpleNamespace(
        context={"task_id": first.task_id, "poll_interval": 0.001},
        index=SimpleNamespace(entry=read),
        response=SimpleNamespace(),
    )
    with pytest.raises(ValueError, match="Task restarted"):
        await WaitTaskStep.execute(step)
    read.reset_mock(side_effect=True)
    read.side_effect = [first, replacement]
    with pytest.raises(ValueError, match="Task restarted"):
        async for _ in TaskEventStream(tmp_path, TaskLogReader(tmp_path), read, get_logger("test")).follow(
            first.task_id, 0.001
        ):
            pass


def test_repeated_children_sync_with_their_latest_start_time(tmp_path):
    configure_logging(LoggingConfig(log_to_console=False, log_to_file=False))

    class Parent(BaseTask):
        def build_task_steps(self):
            yield self.repeat

        def repeat(self):
            self.run_task("demo", x=1, y=2)
            self.run_task("demo", x=10, y=20)

        def build_output_params(self):
            return BaseOutputParams()

    workspace = tmp_path / "source"
    executor = TaskExecutor(resolve_task=lambda _: DemoTask)
    parent = executor.execute(Parent({"task_name": "repeat"}, workspace_path=workspace, reg_name="parent"))
    first, second = parent.children
    assert first.child_task_id == second.child_task_id
    assert first.started_at < second.started_at
    child = read_entry(workspace, second.child_task_id)
    assert child.parent_task_id == parent.task_id
    assert child.started_at == second.started_at
    events = (task_path(workspace, child.task_id) / "events.jsonl").read_text().splitlines()
    assert any(json.loads(event)["state"] == "running" for event in events)
    plans = prepare_group(workspace, parent.task_id, tmp_path / "staging", 1_000_000, TaskLogReader(tmp_path), {})
    archive = tmp_path / "tasks.tar.gz"
    build_archive(plans, list(plans), archive)
    target = tmp_path / "target"
    target.mkdir()
    TaskArchiveApplier(target, 1_000_000).apply(archive, [])
    replica = read_entry(target, parent.task_id)
    assert replica.replica.snapshot.root_started_at == parent.started_at
    assert read_entry(target, child.task_id).started_at == second.started_at
    executor.execute(DemoTask({"task_name": "repeat", "x": 99, "y": 1}, workspace_path=workspace, reg_name="demo"))
    with pytest.raises(SnapshotChangedError, match="Live source Task is unavailable"):
        task_group(workspace, parent.task_id)

    # A pending child must not pull the previous contents of its named directory.
    parent.children[-1].started_at = None
    write_task_metadata(task_path(workspace, parent.task_id), parent)
    assert set(task_group(workspace, parent.task_id)) == {parent.task_id}
