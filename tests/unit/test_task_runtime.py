"""Exercise execution, composition and the Task-owned persistence primitives."""

import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta

import pytest

from axonx.plugin import catalog
from axonx.plugin.models import PluginInfo
from axonx.task.builtins.demo import DemoTask
from axonx.task.core.composite import BaseCompositeTask, ChildTaskError
from axonx.task.models.artifacts import ReplaySource
from axonx.task.models.identity import TaskState
from axonx.task.models.lifecycle import DisplayReplica
from axonx.task.models.params import BaseOutputParams
from axonx.task.runtime.executor import TaskExecutor
from axonx.task.runtime.replay import ReplayClock, ReplayCursor
from axonx.task.runtime.runner import TaskRunner
from axonx.task.storage.files import atomic_write, snapshot_file
from axonx.task.storage.locking import file_lock
from axonx.task.storage.replay import ReplayStream
from axonx.task.storage.workspace import read_entry, resolve_relative_path, task_path, write_task_metadata
from axonx.utils.logging import LoggingConfig, configure_logging


class ParentOutput(BaseOutputParams):
    result: int


class ParentTask(BaseCompositeTask):
    output_cls = ParentOutput

    def build_task_steps(self):
        yield self.add

    def add(self):
        self.state["result"] = self.run_task("demo", x=2, y=3).output["result"]

    def build_output_params(self):
        return ParentOutput(result=self.state["result"])


def test_executor_resolves_and_runs_child_tasks(tmp_path):
    configure_logging(LoggingConfig(log_to_console=False, log_to_file=False))
    resolved = []

    def resolve(name):
        resolved.append(name)
        return {"parent": ParentTask, "demo": DemoTask}[name]

    result = TaskExecutor(tmp_path, resolve_task=resolve).execute("parent", {"task_name": "nested"})
    assert result.state == TaskState.SUCCEEDED
    assert result.output_params["result"] == 5
    assert resolved == ["parent", "demo"]
    child = result.children[0]
    assert child.state == TaskState.SUCCEEDED
    assert read_entry(tmp_path, child.task_id).parent_task_id == result.task_id


def test_nested_composites_inherit_the_execution_context_and_clock(tmp_path):
    configure_logging(LoggingConfig(log_to_console=False, log_to_file=False))
    captured = {}

    class Leaf(DemoTask):
        def initialize(self):
            captured["leaf"] = self
            super().initialize()

    class Middle(BaseCompositeTask):
        def build_task_steps(self):
            yield lambda: self.run_task("leaf", task_name="explicit", x=1, y=2)

    class Root(BaseCompositeTask):
        def build_task_steps(self):
            yield lambda: self.run_task("middle")

    root = Root(
        {},
        workspace_path=tmp_path,
        reg_name="root",
        timezone="America/New_York",
        clock=ReplayClock(datetime(2026, 1, 1, tzinfo=UTC)),
    )
    resolved = []

    def resolve(name):
        resolved.append(name)
        return {"middle": Middle, "leaf": Leaf}[name]

    status = TaskRunner(resolve_task=resolve).run(root)
    leaf = captured["leaf"]
    assert status.state == TaskState.SUCCEEDED
    assert resolved == ["middle", "leaf"]
    assert leaf.clock is root.clock
    assert leaf.context.timezone == root.context.timezone == "America/New_York"
    assert leaf.created_at.tzinfo == root.created_at.tzinfo
    assert leaf.context.source == root.context.source
    assert leaf.workspace_path == root.workspace_path
    assert leaf.input_params.task_name == "explicit"
    assert leaf.context.parent_task_id == status.children[0].task_id
    with pytest.raises(RuntimeError, match="inside the parent TaskRunner"):
        root.run_task("middle")


@pytest.mark.parametrize("invalid_input", [False, True])
def test_continue_after_child_failure_keeps_the_parent_failed(tmp_path, invalid_input):
    configure_logging(LoggingConfig(log_to_console=False, log_to_file=False))

    class Parent(BaseCompositeTask):
        def build_task_steps(self):
            yield self.children_steps

        def children_steps(self):
            inputs = {"x": "invalid", "y": 2} if invalid_input else {"x": 1, "y": 2, "fail": True}
            result = self.run_task("demo", node_name="first", on_error="continue", **inputs)
            assert not result.success
            assert (result.record.task_id is None) == invalid_input
            self.run_task("demo", node_name="second", x=3, y=4)

    status = TaskExecutor(tmp_path, resolve_task=lambda name: Parent if name == "parent" else DemoTask).execute(
        "parent", {"task_name": "continue"}
    )
    assert status.state == TaskState.FAILED
    assert status.exit_code == 1
    assert [child.state for child in status.children] == [TaskState.FAILED, TaskState.SUCCEEDED]
    assert status.children[0].error
    assert read_entry(tmp_path, status.children[1].task_id).output_params["result"] == 7


def test_composite_without_a_resolver_records_the_failure_and_disconnects_execution(tmp_path):
    configure_logging(LoggingConfig(log_to_console=False, log_to_file=False))
    task = ParentTask({}, workspace_path=tmp_path, reg_name="parent")
    with pytest.raises(ChildTaskError, match="require a task resolver"):
        TaskRunner().run(task)
    status = read_entry(tmp_path, task.task_id)
    assert status.state == TaskState.FAILED
    assert status.children[0].task_id is None
    assert status.children[0].state == TaskState.FAILED
    with pytest.raises(RuntimeError, match="inside the parent TaskRunner"):
        task.run_task("demo", x=1, y=2)


def test_child_is_closed_when_parent_publication_fails_before_child_execution(tmp_path, monkeypatch):
    configure_logging(LoggingConfig(log_to_console=False, log_to_file=False))
    closed = []

    class Child(DemoTask):
        def close(self):
            closed.append(self.task_id)

    runner = TaskRunner(resolve_task=lambda _: Child)
    publish = runner._publish
    rejected = False

    def reject_child():
        nonlocal rejected
        if not rejected and runner.status.children and runner.status.children[0].task_id:
            rejected = True
            raise OSError("parent write failed")
        publish()

    monkeypatch.setattr(runner, "_publish", reject_child)
    parent = ParentTask({}, workspace_path=tmp_path, reg_name="parent")
    with pytest.raises(ChildTaskError, match="parent write failed"):
        runner.run(parent)
    assert closed == ["base#demo#" + parent.input_params.task_name]
    assert read_entry(tmp_path, parent.task_id).state == TaskState.FAILED
    assert read_entry(tmp_path, closed[0]) is None


def test_replay_uses_snapshots_and_delivers_events_strictly_before_the_deadline(tmp_path):
    source = tmp_path / "input.txt"
    source.write_text("original")
    start = datetime(2026, 1, 1, tzinfo=UTC)
    stream = ReplayStream.create(
        tmp_path / "stream",
        [ReplaySource(key="first", available_at=start + timedelta(seconds=1), files={"input": source})],
    )
    source.write_text("changed")
    clock = ReplayClock(start)
    cursor = ReplayCursor(stream, clock)
    consumed = []
    deadline = start + timedelta(seconds=1)
    assert not cursor.wait(deadline, consumed.append, lambda: bool(consumed))
    assert not consumed
    assert cursor.wait(deadline + timedelta(seconds=1), consumed.append, lambda: bool(consumed))
    assert stream.file(consumed[0].files["input"]).read_text() == "original"
    stream.file(consumed[0].files["input"]).write_text("corrupt")
    with pytest.raises(ValueError, match="Replay file changed"):
        ReplayStream(stream.root)


def test_input_resolution_rejects_display_replicas_through_task_authoring_helpers(tmp_path):
    configure_logging(LoggingConfig(log_to_console=False, log_to_file=False))
    source = TaskExecutor(tmp_path, resolve_task=lambda _: DemoTask).execute(
        "demo", {"task_name": "source", "x": 1, "y": 2}
    )
    source.replica = DisplayReplica(source_revision="source", policy_revision="policy", files={})
    directory = task_path(tmp_path, source.task_id)
    write_task_metadata(directory, source)
    consumer = DemoTask({"x": 3, "y": 4}, workspace_path=tmp_path, reg_name="demo")
    for read in (
        lambda: consumer.source_task_dir(source.task_id),
        lambda: consumer.resolve_workspace_path(directory / "data.parquet"),
        lambda: consumer.resolve_workspace_path((directory / "data.parquet").relative_to(tmp_path)),
    ):
        with pytest.raises(ValueError, match="Display replicas"):
            read()
    external = tmp_path.parent / "external-input.parquet"
    assert consumer.resolve_workspace_path(external) == external


def test_failed_task_persists_its_terminal_status(tmp_path):
    configure_logging(LoggingConfig(log_to_console=False, log_to_file=False))
    with pytest.raises(RuntimeError, match="Demo failure requested"):
        TaskExecutor(tmp_path, resolve_task=lambda _: DemoTask).execute(
            "demo", {"task_name": "failure", "x": 1, "y": 2, "fail": True}
        )
    result = read_entry(tmp_path, "base#demo#failure")
    assert result.state == TaskState.FAILED
    assert result.exit_code != 0
    assert "Demo failure requested" in result.error


def test_catalog_only_loads_the_requested_task(monkeypatch):
    plugin = PluginInfo(distribution="example", version="1", tasks={"unrelated": "missing_package:Task"})
    monkeypatch.setattr(catalog, "list_installed_plugins", lambda: [plugin])
    assert catalog.get_task_definition("demo").name == "demo"
    with pytest.raises(ModuleNotFoundError):
        catalog.resolve_task("unrelated")


def test_catalog_rejects_plugin_names_that_shadow_builtins(monkeypatch):
    plugin = PluginInfo(distribution="example", version="1", tasks={"demo": "missing_package:Task"})
    monkeypatch.setattr(catalog, "list_installed_plugins", lambda: [plugin])
    with pytest.raises(ValueError, match="conflict"):
        catalog.resolve_task("demo")


def test_failed_atomic_publication_keeps_the_previous_file(tmp_path):
    target = tmp_path / "metadata.json"
    target.write_text("previous")

    def fail(temporary):
        temporary.write_text("partial")
        raise OSError("disk failure")

    with pytest.raises(OSError, match="disk failure"):
        atomic_write(target, fail)
    assert target.read_text() == "previous"
    assert list(tmp_path.iterdir()) == [target]


def test_isolated_snapshot_is_unchanged_when_source_is_rewritten(tmp_path):
    source, target = tmp_path / "source", tmp_path / "snapshot"
    source.write_text("original")
    snapshot_file(source, target, isolated=True)
    source.write_text("changed")
    assert target.read_text() == "original"


@pytest.mark.parametrize("path", ["", ".", "../outside", "/absolute"])
def test_task_mutation_paths_stay_inside_the_workspace(tmp_path, path):
    with pytest.raises(ValueError):
        resolve_relative_path(tmp_path, path)


def test_task_mutation_paths_reject_symlink_segments(tmp_path):
    (tmp_path / "link").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match="symlinks"):
        resolve_relative_path(tmp_path, "link/metadata.json")


def test_online_publishers_cannot_enter_another_process_transaction(tmp_path):
    path = tmp_path / "publication.lock"
    code = (
        "import fcntl,sys; from pathlib import Path; "
        f"handle=Path({str(path)!r}).open('a+b'); fcntl.flock(handle,fcntl.LOCK_EX); "
        "print('ready',flush=True); sys.stdin.read()"
    )
    with subprocess.Popen(
        [sys.executable, "-c", code], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True
    ) as child:
        assert child.stdout.readline().strip() == "ready"
        with pytest.raises(BlockingIOError):
            with file_lock(path):
                pytest.fail("Entered another writer's transaction")
        child.communicate(timeout=5)
    with file_lock(path):
        assert os.path.isfile(path)
