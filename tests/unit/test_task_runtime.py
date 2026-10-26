"""Exercise execution, composition and the Task-owned persistence primitives."""

import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import Field

from axonx.plugin import catalog
from axonx.plugin.models import PluginInfo
from axonx.task.builtins.demo import DemoTask
from axonx.task.core.base import BaseTask, ChildTaskError
from axonx.task.models.artifacts import ReplaySource
from axonx.task.models.events import ProgressEvent
from axonx.task.models.identity import TaskState, TaskType
from axonx.task.models.lifecycle import DisplayReplica
from axonx.task.models.params import BaseOutputParams
from axonx.task.runtime import progress
from axonx.task.runtime.executor import TaskExecutor
from axonx.task.runtime.replay import ReplayClock, ReplayCursor
from axonx.task.storage.files import atomic_write, file_lock, snapshot_file
from axonx.task.storage.logs import TaskJournal
from axonx.task.storage.replay import ReplayStream
from axonx.task.storage.workspace import read_entry, resolve_relative_path, task_path, write_task_metadata
from axonx.utils.logging import LoggingConfig, configure_logging


class ParentOutput(BaseOutputParams):
    result: int


class ParentTask(BaseTask):
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

    task = resolve("parent")({"task_name": "nested"}, workspace_path=tmp_path, reg_name="parent")
    result = TaskExecutor(resolve_task=resolve).execute(task)
    assert result.state == TaskState.SUCCEEDED
    assert result.output_params["result"] == 5
    assert resolved == ["parent", "demo"]
    child = result.children[0]
    assert child.state == TaskState.SUCCEEDED
    assert read_entry(tmp_path, child.child_task_id).parent_task_id == result.task_id


@pytest.mark.parametrize("parent_code, child_code, expected", [(0, 0, 0), (0, 7, 7), (9, 0, 9), (9, 7, 9)])
def test_business_tasks_keep_their_steps_outputs_and_type_when_calling_children(
    tmp_path, parent_code, child_code, expected
):
    class Child(DemoTask):
        task_type = TaskType.ETL

        @staticmethod
        def exit_code(_output):
            return child_code

    class Parent(DemoTask):
        task_type = TaskType.TRAIN

        def initialize(self):
            result = self.run_task(reg_name="child", x=3, y=4, on_error="continue")
            assert result.child_task_id == "etl#child#parent"
            assert result.output["result"] == 7
            assert result.success == (child_code == 0)
            result.record.error = "detached result"
            self.children[0].error = "detached children"
            super().initialize()

        @staticmethod
        def exit_code(_output):
            return parent_code

    parent = Parent(
        {"task_name": "parent", "x": 5, "y": 6, "upstream_task_ids": ["etl#source#upstream"]},
        workspace_path=tmp_path,
        reg_name="parent",
    )
    status = TaskExecutor(resolve_task=lambda _: Child).execute(parent)
    assert status.task_type == TaskType.TRAIN
    assert status.exit_code == expected
    assert status.state == (TaskState.FAILED if expected else TaskState.SUCCEEDED)
    assert status.steps[0].name == "initialize"
    assert status.output_params["result"] == 11
    invocation = status.children[0]
    assert invocation.reg_name == "child"
    assert "detached" not in invocation.error
    child = read_entry(tmp_path, invocation.child_task_id)
    assert child.parent_task_id == parent.task_id
    assert child.task_type == TaskType.ETL
    assert child.input_params["upstream_task_ids"] == []


@pytest.mark.parametrize(
    "sources",
    ["etl#data#first, train#model#second", '["etl#data#first", "train#model#second"]'],
)
def test_cli_converts_upstream_task_arguments_before_execution(tmp_path, sources):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "axonx.cli",
            "exec",
            "--task",
            "demo",
            "--task-name",
            "sources",
            "--x",
            "2",
            "--y",
            "3",
            "--upstream-task-ids",
            sources,
            "--workspace-dir",
            str(tmp_path),
            "--log-dir",
            str(tmp_path / "logs"),
        ],
        env={**os.environ, "AXONX_SERVICE_TARGET": "http://127.0.0.1:9"},
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    metadata = read_entry(tmp_path, "base#demo#sources")
    assert metadata.input_params["upstream_task_ids"] == ["etl#data#first", "train#model#second"]
    assert metadata.output_params["result"] == 5


def test_task_identity_is_derived_and_cannot_be_its_own_upstream(tmp_path):
    with pytest.raises(ValueError, match="own Task ID"):
        DemoTask(
            {"task_name": "self", "x": 1, "y": 2, "upstream_task_ids": ["base#demo#self"]},
            workspace_path=tmp_path,
            reg_name="demo",
        )


def test_named_progress_substeps_are_published_to_the_task_journal(tmp_path):
    configure_logging(LoggingConfig(log_to_console=False, log_to_file=False))

    class ReportingTask(DemoTask):
        def initialize(self):
            self.report_progress(10, name="part", state="running")
            super().initialize()
            self.report_progress(100, name="part", state="done")

    task = ReportingTask({"x": 1, "y": 2}, workspace_path=tmp_path, reg_name="demo")
    assert TaskExecutor().execute(task).state == TaskState.SUCCEEDED
    _, lines = TaskJournal(task.task_dir / "events.jsonl").read(0)
    events = [ProgressEvent.model_validate_json(line) for line in lines]
    assert {event.state for event in events if event.name == "part"} == {"running", "done"}
    assert next(step for step in read_entry(tmp_path, task.task_id).steps if step.name == "part").percentage == 100


@pytest.mark.parametrize("fail", [False, True])
def test_throttled_progress_is_flushed_before_terminal_metadata(tmp_path, monkeypatch, fail):
    configure_logging(LoggingConfig(log_to_console=False, log_to_file=False))
    monkeypatch.setattr(progress, "perf_counter", lambda: 100)
    write_metadata = progress.write_task_metadata
    terminal_states = []

    def observe_terminal(directory, status):
        if status.state.is_terminal:
            _, lines = TaskJournal(directory / "events.jsonl").read(0)
            events = [ProgressEvent.model_validate_json(line) for line in lines]
            latest = next(event for event in reversed(events) if event.name == "part")
            assert latest.percentage == 20
            assert latest.state == ("failed" if fail else "skipped")
            terminal_states.append(status.state)
        write_metadata(directory, status)

    monkeypatch.setattr(progress, "write_task_metadata", observe_terminal)

    class ReportingTask(DemoTask):
        def initialize(self):
            super().initialize()
            self.report_progress(10, name="part", state="running")
            journal = self.task_dir / "events.jsonl"
            before = journal.read_bytes()
            self.report_progress(20, name="part")
            self.persist_metadata()
            assert journal.read_bytes() == before

    task = ReportingTask({"x": 1, "y": 2, "fail": fail}, workspace_path=tmp_path, reg_name="demo")
    if fail:
        with pytest.raises(RuntimeError, match="Demo failure requested"):
            TaskExecutor().execute(task)
    else:
        TaskExecutor().execute(task)
    assert terminal_states == [TaskState.FAILED if fail else TaskState.SUCCEEDED]


def test_executor_can_run_another_task_after_failure(tmp_path):
    configure_logging(LoggingConfig(log_to_console=False, log_to_file=False))
    executor = TaskExecutor()
    failed = DemoTask({"x": 1, "y": 2, "fail": True}, workspace_path=tmp_path, reg_name="failed")
    with pytest.raises(RuntimeError, match="Demo failure requested"):
        executor.execute(failed)
    succeeded = DemoTask({"x": 3, "y": 4}, workspace_path=tmp_path, reg_name="succeeded")
    assert executor.execute(succeeded).output_params["result"] == 7
    with pytest.raises(RuntimeError, match="inside the TaskExecutor"):
        failed.report_progress(100)
    assert read_entry(tmp_path, failed.task_id).state == TaskState.FAILED


def test_failed_step_keeps_progress_available_until_cleanup_finishes(tmp_path):
    class ClosingTask(DemoTask):
        def initialize(self):
            self.report_progress(10, name="worker", state="running")
            raise ValueError("setup failed")

        def close(self):
            self.state["closed"] = self.state.get("closed", 0) + 1
            self.report_progress(100, name="worker", state="done")

    task = ClosingTask({"x": 1, "y": 2}, workspace_path=tmp_path, reg_name="closing")
    with pytest.raises(ValueError, match="setup failed"):
        TaskExecutor().execute(task)
    status = read_entry(tmp_path, task.task_id)
    assert task.state["closed"] == 1
    assert status.state == TaskState.FAILED
    assert next(step for step in status.steps if step.name == "worker").state == "done"


@pytest.mark.parametrize("return_awaitable", [False, True])
def test_async_steps_are_rejected_and_resources_closed_once(tmp_path, return_awaitable):
    class AsyncTask(DemoTask):
        async def asynchronous(self):
            pytest.fail("An asynchronous step was executed")

        def synchronous(self):
            return self.asynchronous()

        def build_task_steps(self):
            yield self.synchronous if return_awaitable else self.asynchronous

        def close(self):
            self.state["closed"] = self.state.get("closed", 0) + 1

    task = AsyncTask({"x": 1, "y": 2}, workspace_path=tmp_path, reg_name="async")
    with pytest.raises(TypeError, match="returned an awaitable" if return_awaitable else "must be synchronous"):
        TaskExecutor().execute(task)
    assert task.state["closed"] == 1
    assert read_entry(tmp_path, task.task_id).state == TaskState.FAILED


def test_task_logs_include_children_and_exclude_siblings(tmp_path):
    try:
        configure_logging(LoggingConfig(log_dir=tmp_path / "logs", log_to_console=False))
        workspace = tmp_path / "workspace"
        executor = TaskExecutor(resolve_task=lambda _: DemoTask)
        parent = executor.execute(ParentTask({"task_name": "nested"}, workspace_path=workspace, reg_name="parent"))
        child = read_entry(workspace, parent.children[0].child_task_id)
        sibling = executor.execute(
            DemoTask({"task_name": "sibling", "x": 10, "y": 20}, workspace_path=workspace, reg_name="demo")
        )
        parent_log = Path(parent.log_path).read_text(encoding="utf-8")
        child_log = Path(child.log_path).read_text(encoding="utf-8")
        sibling_log = Path(sibling.log_path).read_text(encoding="utf-8")
        assert "Demo initialized x=2 y=3" in parent_log
        assert "Demo initialized x=2 y=3" in child_log
        assert f"Task started task_id={parent.task_id}" not in child_log
        assert "Demo initialized x=10 y=20" not in parent_log + child_log
        assert "Demo initialized x=10 y=20" in sibling_log
        assert "Demo initialized x=2 y=3" not in sibling_log
    finally:
        configure_logging(LoggingConfig(log_to_console=False, log_to_file=False))


def test_incremental_output_is_a_detached_snapshot_and_does_not_complete_the_task(tmp_path):
    class Output(BaseOutputParams):
        counters: dict[str, int] = Field(alias="counts")

    class PublishingTask(DemoTask):
        output_cls = Output

        def initialize(self):
            super().initialize()
            self.state["counters"] = {"seen": 1}
            self.publish_output()
            self.state["counters"]["seen"] = 2
            status = read_entry(tmp_path, self.task_id)
            assert status.state == TaskState.RUNNING
            assert status.output_params["counts"] == {"seen": 1}
            assert self.metadata.output_params["counts"] == {"seen": 1}
            with pytest.raises(RuntimeError, match="before execution completes"):
                _ = self.output_params

        def build_output_params(self):
            return Output(counters=self.state["counters"])

    task = PublishingTask({"x": 1, "y": 2}, workspace_path=tmp_path, reg_name="publish")
    status = TaskExecutor().execute(task)
    assert status.state == TaskState.SUCCEEDED
    assert status.output_params == task.output == {"artifacts": {}, "counts": {"seen": 2}}


@pytest.mark.parametrize("publish", [False, True])
def test_incremental_and_final_output_require_the_declared_model(tmp_path, publish):
    class InvalidOutputTask(DemoTask):
        def initialize(self):
            super().initialize()
            if publish:
                self.publish_output()

        def build_output_params(self):
            return {}

    task = InvalidOutputTask({"x": 1, "y": 2}, workspace_path=tmp_path, reg_name="invalid")
    with pytest.raises(TypeError, match="build_output_params must return"):
        TaskExecutor().execute(task)
    status = read_entry(tmp_path, task.task_id)
    assert status.state == TaskState.FAILED
    assert status.output_params == {}


def test_nested_tasks_inherit_the_execution_context_and_clock(tmp_path):
    configure_logging(LoggingConfig(log_to_console=False, log_to_file=False))
    captured = {}

    class Leaf(DemoTask):
        def initialize(self):
            captured["leaf"] = self
            parent = read_entry(self.workspace_path, self.context.parent_task_id)
            invocation = parent.children[-1]
            assert parent.state == invocation.state == TaskState.RUNNING
            assert invocation.child_task_id == self.task_id
            assert invocation.started_at == self.metadata.started_at
            super().initialize()

    class Middle(BaseTask):
        def build_task_steps(self):
            yield lambda: self.run_task("leaf", task_name="explicit", x=1, y=2)

        def build_output_params(self):
            return BaseOutputParams()

    class Root(BaseTask):
        def build_task_steps(self):
            yield lambda: self.run_task("middle")

        def build_output_params(self):
            return BaseOutputParams()

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

    status = TaskExecutor(resolve_task=resolve).execute(root)
    leaf = captured["leaf"]
    assert status.state == TaskState.SUCCEEDED
    assert resolved == ["middle", "leaf"]
    assert leaf.clock is root.clock
    assert leaf.context.timezone == root.context.timezone == "America/New_York"
    assert leaf.created_at.tzinfo == root.created_at.tzinfo
    assert leaf.workspace_path == root.workspace_path
    assert leaf.input_params.task_name == "explicit"
    assert leaf.context.parent_task_id == status.children[0].child_task_id
    with pytest.raises(RuntimeError, match="inside the parent TaskExecutor"):
        root.run_task("middle")


@pytest.mark.parametrize("invalid_input", [False, True])
def test_continue_after_child_failure_keeps_the_parent_failed(tmp_path, invalid_input):
    configure_logging(LoggingConfig(log_to_console=False, log_to_file=False))

    class Parent(BaseTask):
        def build_task_steps(self):
            yield self.children_steps

        def children_steps(self):
            inputs = {"x": "invalid", "y": 2} if invalid_input else {"x": 1, "y": 2, "fail": True}
            result = self.run_task("demo", node_name="first", on_error="continue", **inputs)
            assert not result.success
            assert (result.record.child_task_id is None) == invalid_input
            self.run_task("demo", node_name="second", x=3, y=4)

        def build_output_params(self):
            return BaseOutputParams()

    status = TaskExecutor(resolve_task=lambda _: DemoTask).execute(
        Parent({"task_name": "continue"}, workspace_path=tmp_path, reg_name="parent")
    )
    assert status.state == TaskState.FAILED
    assert status.exit_code == 1
    assert [child.state for child in status.children] == [TaskState.FAILED, TaskState.SUCCEEDED]
    assert status.children[0].error
    assert read_entry(tmp_path, status.children[1].child_task_id).output_params["result"] == 7


def test_successful_retry_keeps_the_failed_invocation_and_parent_outcome(tmp_path):
    class Parent(ParentTask):
        def add(self):
            self.run_task("demo", x=1, y=2, fail=True, on_error="continue")
            super().add()

    status = TaskExecutor(resolve_task=lambda _: DemoTask).execute(
        Parent({"task_name": "retry"}, workspace_path=tmp_path, reg_name="parent")
    )
    first, second = status.children
    assert first.child_task_id == second.child_task_id
    assert (first.attempt, second.attempt) == (1, 2)
    assert first.started_at < second.started_at
    assert (first.state, second.state) == (TaskState.FAILED, TaskState.SUCCEEDED)
    assert read_entry(tmp_path, second.child_task_id).state == TaskState.SUCCEEDED
    assert status.output_params["result"] == 5
    assert status.state == TaskState.FAILED


def test_parent_without_a_resolver_records_the_failure_and_disconnects_execution(tmp_path):
    configure_logging(LoggingConfig(log_to_console=False, log_to_file=False))
    task = ParentTask({}, workspace_path=tmp_path, reg_name="parent")
    with pytest.raises(ChildTaskError, match="require a task resolver"):
        TaskExecutor().execute(task)
    status = read_entry(tmp_path, task.task_id)
    assert status.state == TaskState.FAILED
    assert status.children[0].child_task_id is None
    assert status.children[0].state == TaskState.FAILED
    with pytest.raises(RuntimeError, match="inside the parent TaskExecutor"):
        task.run_task("demo", x=1, y=2)


@pytest.mark.parametrize("interruption", [KeyboardInterrupt, SystemExit])
def test_continue_policy_propagates_child_interruptions_after_recording_them(tmp_path, interruption):
    class InterruptedChild(DemoTask):
        def initialize(self):
            raise interruption("interrupted")

    class Parent(BaseTask):
        def build_task_steps(self):
            yield lambda: self.run_task("child", on_error="continue", x=1, y=2)

        def build_output_params(self):
            return BaseOutputParams()

    task = Parent({}, workspace_path=tmp_path, reg_name="parent")
    with pytest.raises(interruption, match="interrupted"):
        TaskExecutor(resolve_task=lambda _: InterruptedChild).execute(task)
    status = read_entry(tmp_path, task.task_id)
    child = status.children[0]
    assert status.state == child.state == TaskState.FAILED
    assert child.exit_code == 1
    assert child.error == f"{interruption.__name__}: interrupted"
    assert read_entry(tmp_path, child.child_task_id).state == TaskState.FAILED


def test_child_is_closed_when_parent_publication_fails_before_child_execution(tmp_path, monkeypatch):
    configure_logging(LoggingConfig(log_to_console=False, log_to_file=False))
    closed = []

    class Child(DemoTask):
        def close(self):
            closed.append(self.task_id)

    executor = TaskExecutor(resolve_task=lambda _: Child)
    publish = progress.write_task_metadata
    rejected = False

    def reject_child(directory, status):
        nonlocal rejected
        if not rejected and status.children and status.children[0].child_task_id:
            rejected = True
            raise OSError("parent write failed")
        publish(directory, status)

    monkeypatch.setattr(progress, "write_task_metadata", reject_child)
    parent = ParentTask({}, workspace_path=tmp_path, reg_name="parent")
    with pytest.raises(ChildTaskError, match="parent write failed"):
        executor.execute(parent)
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
    with pytest.raises(ValueError, match="Artifact revision mismatch"):
        ReplayStream(stream.root)


def test_input_resolution_rejects_display_replicas_through_task_authoring_helpers(tmp_path):
    configure_logging(LoggingConfig(log_to_console=False, log_to_file=False))
    source = TaskExecutor().execute(
        DemoTask({"task_name": "source", "x": 1, "y": 2}, workspace_path=tmp_path, reg_name="demo")
    )
    source.replica = DisplayReplica(source_revision="source", policy_revision="policy", files={})
    directory = task_path(tmp_path, source.task_id)
    write_task_metadata(directory, source)
    consumer = DemoTask({"x": 3, "y": 4}, workspace_path=tmp_path, reg_name="demo")
    for read in (
        lambda: consumer.upstream_task_dir(source.task_id),
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
        TaskExecutor().execute(
            DemoTask({"task_name": "failure", "x": 1, "y": 2, "fail": True}, workspace_path=tmp_path, reg_name="demo")
        )
    result = read_entry(tmp_path, "base#demo#failure")
    assert result.state == TaskState.FAILED
    assert result.exit_code != 0
    assert "Demo failure requested" in result.error


def test_catalog_only_loads_the_requested_task(monkeypatch):
    plugin = PluginInfo(distribution="example", version="1", tasks={"unrelated": "missing_package:Task"})
    monkeypatch.setattr(catalog, "list_installed_plugins", lambda: [plugin])
    tasks = catalog.TaskCatalog()
    assert tasks.definition("demo").name == "demo"
    with pytest.raises(ModuleNotFoundError):
        tasks.resolve("unrelated")


def test_catalog_rejects_plugin_names_that_shadow_builtins(monkeypatch):
    plugin = PluginInfo(distribution="example", version="1", tasks={"demo": "missing_package:Task"})
    monkeypatch.setattr(catalog, "list_installed_plugins", lambda: [plugin])
    with pytest.raises(ValueError, match="conflict"):
        catalog.TaskCatalog()


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
