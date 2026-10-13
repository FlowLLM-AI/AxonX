"""Composite Tasks preserve child contracts, ownership, and failure semantics."""

import asyncio
import json
import os
import re
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from axonx.components.task_manager.local.manager import LocalTaskManager
from axonx.components.task_manager.local.supervisor import (
    TaskProcessSupervisor,
    WorkerExit,
)
from axonx.components.task_repository import LocalTaskRepository
from axonx.core import Application
from axonx.enums import TaskState, TaskType
from axonx.plugin_kit.models import PluginInfo
from axonx.task import BaseCompositeTask, BaseOutputParams, BaseTask, ChildTaskError
from axonx.task.builtins.demo import DemoTask, DemoTaskOutputParams
from axonx.task.catalog import get_task_definition
from axonx.task.runtime.executor import TaskCommandExecutor
from axonx.task.runtime.runner import TaskRunner
from axonx.task.storage.artifacts import artifact_path, artifact_record, read_metadata

from axonx.task.storage.workspace import (
    METADATA_FILE,
    ChildTaskRecord,
    TaskMetadata,
    read_task_metadata,
    task_path,
    write_task_metadata,
)


class Composite(BaseCompositeTask):
    """Let each test supply a small synchronous composition."""

    def __init__(self, *args, compose, **kwargs):
        super().__init__(*args, **kwargs)
        self.compose = compose

    def build_task_steps(self):
        yield self.execute_children

    def execute_children(self):
        self.compose(self)


def parent(tmp_path, compose, **kwargs):
    inputs = kwargs.pop("input_params", {})
    return Composite(inputs, workspace_path=tmp_path, reg_name="composite", compose=compose, **kwargs)


def composition(task):
    return read_task_metadata(task.task_dir, task.task_id)


def test_child_logs_are_isolated_and_parent_keeps_complete_chain(tmp_path, monkeypatch):
    from axonx.utils.logging import LoggingConfig, configure_logging

    class LoggedTask(DemoTask):
        def finish(self):
            self.logger.info(f"child-marker-{self.reg_name}")
            super().finish()

    monkeypatch.setattr("axonx.task.catalog.resolver.resolve_task", lambda _name: LoggedTask)
    configure_logging(LoggingConfig(log_dir=tmp_path / "logs", log_to_console=False))
    try:
        task = parent(tmp_path / "workspace", lambda p: [p.run_task(name, x=1, y=2) for name in ("feature", "train")])
        status = TaskRunner().run(task)
        children = [read_task_metadata(task_path(task.workspace_path, c.task_id), c.task_id) for c in task.children]
        assert len({status.log_path, *(c.log_path for c in children)}) == 3
        first, second = [Path(c.log_path).read_text(encoding="utf-8") for c in children]
        assert "child-marker-feature" in first
        assert "child-marker-train" not in first
        assert "child-marker-train" in second
        assert "child-marker-feature" not in second
        complete = Path(status.log_path).read_text(encoding="utf-8")
        assert "child-marker-feature" in complete and "child-marker-train" in complete
        assert "Task completed" in first and "Task completed" in second
    finally:
        configure_logging(LoggingConfig(log_to_console=False, log_to_file=False))


def test_log_setup_failure_closes_task_without_publishing_metadata(tmp_path, monkeypatch):
    task = DemoTask({"x": 1, "y": 2}, workspace_path=tmp_path, reg_name="demo")
    task.close = Mock()
    monkeypatch.setattr("axonx.task.runtime.runner.task_log_scope", Mock(side_effect=OSError("log unavailable")))
    with pytest.raises(OSError, match="log unavailable"):
        TaskRunner().run(task)
    task.close.assert_called_once()
    assert not task.metadata_path.exists()


def test_sequence_loops_output_binding_and_explicit_lineage(tmp_path, monkeypatch):
    monkeypatch.setattr("axonx.task.catalog.resolver.resolve_task", lambda _name: DemoTask)
    results = []

    def compose(task):
        first = task.run_task("source", node_name="sum", x=2, y=3)
        assert isinstance(first.output_params, DemoTaskOutputParams)
        for index in range(3):
            results.append(
                task.run_task(
                    "demo",
                    node_name=f"feature-{index}",
                    x=first.output["result"],
                    y=index,
                    source_tasks=first.task_id,
                )
            )
            current = read_task_metadata(task_path(tmp_path, results[-1].task_id), results[-1].task_id)
            assert current.input_params["source_tasks"] == first.task_id
            assert current.run_id == results[-1].run_id
        # Numeric outputs are invocation snapshots, independent of overwritten directories.
        for index, result in enumerate(results):
            task.run_task("demo", node_name=f"predict-{index}", x=result.output["result"], y=1)

    task = parent(tmp_path, compose)
    status = TaskRunner().run(task)

    assert status.state == TaskState.SUCCEEDED
    assert [result.output["result"] for result in results] == [5, 6, 7]
    assert [child.node_name for child in task.children] == [
        "sum",
        "feature-0",
        "feature-1",
        "feature-2",
        "predict-0",
        "predict-1",
        "predict-2",
    ]
    for child in task.children:
        directory = task_path(tmp_path, child.task_id)
        child_status = read_task_metadata(directory, child.task_id)
        assert child_status.state == TaskState.SUCCEEDED
        assert child_status.pid == os.getpid()
        assert child_status.run_id == (task.children[0].run_id if child.task == "source" else task.children[-1].run_id)
        assert child.run_id != task.context.run_id
        assert (directory / "metadata.json").is_file()
    first_status = read_task_metadata(task_path(tmp_path, task.children[0].task_id), task.children[0].task_id)
    assert first_status.input_params["source_tasks"] == ""
    assert len({child.run_id for child in task.children}) == 7
    assert len({child.task_id for child in task.children}) == 2
    metadata = json.loads(task.metadata_path.read_text())
    assert metadata["children"] == [child.model_dump(mode="json") for child in task.children]
    assert not (task.task_dir / "status.json").exists()
    assert not (task.task_dir / "composition.json").exists()
    assert composition(task).children == list(task.children)


@pytest.mark.parametrize("parent_name", ["pipeline", "a" * 32])
def test_file_pipeline_consumes_each_output_before_replacement(tmp_path, monkeypatch, parent_name):
    class FileOutput(BaseOutputParams):
        result: int

    class FileTask(DemoTask):
        output_cls = FileOutput

        def build_task_steps(self):
            yield self.transform

        def transform(self):
            sources = self.input_params.source_tasks
            if sources:
                directory = self.source_task_dir(sources)
                upstream = int(
                    artifact_path(directory, read_metadata(directory / "metadata.json"), "value").read_text()
                )
            else:
                upstream = self.input_params.x
            self.state["result"] = upstream + self.input_params.y
            (self.task_dir / "value.txt").write_text(str(self.state["result"]))

        def build_output_params(self):
            return self.output_cls(
                result=self.state["result"],
                artifacts={"value": artifact_record(self.task_dir / "value.txt", self.task_dir)},
            )

    monkeypatch.setattr("axonx.task.catalog.resolver.resolve_task", lambda _name: FileTask)

    def compose(task):
        predictions = []
        for index in range(3):
            feature = task.run_task("feature", node_name=f"feature-{index}", x=index, y=10)
            predictions.append(task.run_task("predict", x=0, y=100, source_tasks=feature.task_id))
        assert [prediction.output["result"] for prediction in predictions] == [
            110,
            111,
            112,
        ]
        assert (task_path(tmp_path, feature.task_id) / "value.txt").read_text() == "12"
        assert (task_path(tmp_path, predictions[-1].task_id) / "value.txt").read_text() == "112"

    first = parent(tmp_path, compose, input_params={"task_name": parent_name})
    TaskRunner().run(first)
    assert len({child.task_id for child in first.children}) == 2
    second = parent(tmp_path, compose, input_params={"task_name": parent_name})
    TaskRunner().run(second)
    assert [child.task_id for child in first.children] == [child.task_id for child in second.children]
    assert {child.run_id for child in first.children}.isdisjoint(child.run_id for child in second.children)


def test_nested_composites_and_separate_parents_inherit_the_same_name(tmp_path, monkeypatch):
    class Nested(BaseCompositeTask):
        def build_task_steps(self):
            yield lambda: self.run_task("demo", x=1, y=2)

    monkeypatch.setattr(
        "axonx.task.catalog.resolver.resolve_task",
        lambda name: Nested if name == "nested" else DemoTask,
    )
    results = []

    def compose(task):
        results.append(task.run_task("nested", node_name="left"))
        results.append(task.run_task("nested", node_name="right"))

    for name in ("first", "second"):
        task = Composite(
            {"task_name": "shared"},
            workspace_path=tmp_path,
            reg_name=name,
            compose=compose,
        )
        TaskRunner().run(task)
    assert {result.task_id for result in results} == {"composite#nested#shared"}
    assert len({result.run_id for result in results}) == 4
    nested = read_task_metadata(task_path(tmp_path, results[-1].task_id), results[-1].task_id)
    assert nested.children[0].task_id == "base#demo#shared"
    latest = results[-1]
    assert read_task_metadata(task_path(tmp_path, latest.task_id), latest.task_id).run_id == latest.run_id


@pytest.mark.parametrize("change", ["replacement", "deletion"])
def test_child_startup_recovery_preserves_replacement_or_deleted_directory(tmp_path, monkeypatch, change):
    task = parent(tmp_path, lambda owner: owner.run_task("demo", x=1, y=2, on_error="continue"))
    write_record = task.persist_metadata
    changed = False

    def change_before_handoff():
        nonlocal changed
        if task.children and task.children[0].state == TaskState.RUNNING and not changed:
            changed = True
            child = task.children[0]
            directory = task_path(tmp_path, child.task_id)
            if change == "replacement":
                directory.mkdir(parents=True)
                write_task_metadata(
                    directory,
                    TaskMetadata(
                        version=1,
                        task_id=child.task_id,
                        run_id="replacement",
                        task_type=TaskType.BASE,
                        state=TaskState.QUEUED,
                    ),
                )
            else:
                shutil.rmtree(directory, ignore_errors=True)
            raise OSError("handoff failed")
        write_record()

    monkeypatch.setattr(task, "persist_metadata", change_before_handoff)
    assert TaskRunner().run(task).state == TaskState.FAILED
    assert changed
    child = task.children[0]
    directory = task_path(tmp_path, child.task_id)
    if change == "replacement":
        status = read_task_metadata(directory, child.task_id)
        assert status.run_id == "replacement"
        assert status.state == TaskState.QUEUED
    else:
        assert not directory.exists()


def test_fail_fast_retains_failed_child_and_skips_later_work(tmp_path):
    def compose(task):
        task.run_task("demo", x=1, y=2, fail=True)
        task.run_task("demo", x=3, y=4)

    task = parent(tmp_path, compose)
    with pytest.raises(ChildTaskError, match="Demo failure requested") as failure:
        TaskRunner().run(task)

    assert failure.value.result.success is False
    assert failure.value.result.task_id == task.children[0].task_id
    assert read_task_metadata(task.task_dir, task.task_id).state == TaskState.FAILED
    assert len(composition(task).children) == 1
    assert task.children[0].state == TaskState.FAILED
    assert (
        read_task_metadata(task_path(tmp_path, task.children[0].task_id), task.children[0].task_id).state
        == TaskState.FAILED
    )
    assert read_task_metadata(task.task_dir, task.task_id).state == TaskState.FAILED


@pytest.mark.parametrize("failure", ["exception", "exit_code", "validation", "resolution"])
def test_continue_records_failure_runs_later_child_and_fails_parent(tmp_path, monkeypatch, failure):
    class NonzeroTask(DemoTask):
        @staticmethod
        def exit_code(_output):
            return 7

    if failure == "exit_code":
        monkeypatch.setattr("axonx.task.catalog.resolver.resolve_task", lambda _name: NonzeroTask)

    results = []

    def compose(task):
        inputs = {"x": 1, "y": 2}
        if failure == "exception":
            inputs["fail"] = True
        if failure == "validation":
            inputs.pop("x")
        name = "absent-task" if failure == "resolution" else "demo"
        results.append(task.run_task(name, node_name="first", on_error="continue", **inputs))
        # Resolve the succeeding child independently of the failing definition.
        if failure == "exit_code":
            monkeypatch.setattr("axonx.task.catalog.resolver.resolve_task", lambda _name: DemoTask)
        results.append(task.run_task("demo", node_name="second", x=3, y=4))

    task = parent(tmp_path, compose)
    status = TaskRunner().run(task)

    assert [result.success for result in results] == [False, True]
    assert status.state == TaskState.FAILED
    assert status.exit_code == (7 if failure == "exit_code" else 1)
    assert status.children[0].error
    assert composition(task).children[1].state == TaskState.SUCCEEDED
    assert read_task_metadata(task.task_dir, task.task_id).state == TaskState.FAILED
    if failure == "exit_code":
        assert results[0].output["result"] == 3
    else:
        with pytest.raises(RuntimeError, match="output is unavailable"):
            _ = results[0].output


def test_children_keep_attempt_records_and_replace_outputs_on_parent_rerun(tmp_path):
    def compose(task):
        task.run_task("demo", node_name="repeated", x=1, y=2)
        task.run_task("demo", node_name="repeated", x=2, y=3)

    first = parent(tmp_path, compose, input_params={"task_name": "named"})
    TaskRunner().run(first)
    snapshots = {
        child.task_id: (task_path(tmp_path, child.task_id) / "metadata.json").read_bytes() for child in first.children
    }
    second = parent(tmp_path, compose, input_params={"task_name": "named"})
    TaskRunner().run(second)

    assert first.task_id == second.task_id
    assert [child.attempt for child in first.children] == [1, 2]
    assert len({child.task_id for child in (*first.children, *second.children)}) == 1
    assert len({child.run_id for child in (*first.children, *second.children)}) == 4
    for task_id, before in snapshots.items():
        assert (task_path(tmp_path, task_id) / "metadata.json").read_bytes() != before


def test_child_names_replace_terminal_outputs_and_keep_independent_runs(tmp_path):
    results = []

    def compose(task):
        results.append(task.run_task("demo", x=2, y=3))

    first = parent(tmp_path, compose, input_params={"task_name": "research-core"})
    TaskRunner().run(first)
    directory = task_path(tmp_path, results[0].task_id)
    (directory / "obsolete.txt").write_text("old")
    history = directory / "persistent/signals.jsonl"
    history.parent.mkdir()
    history.write_text("retained history\n")
    second = parent(tmp_path, compose, input_params={"task_name": "research-core"})
    TaskRunner().run(second)
    assert first.task_id == "composite#composite#research-core"
    assert first.task_dir.parent.name == "composite"
    assert results[0].task_id == results[1].task_id
    assert results[0].task_id == "base#demo#research-core"
    assert results[0].run_id != results[1].run_id
    assert not (directory / "obsolete.txt").exists()
    assert history.read_text() == "retained history\n"
    assert read_task_metadata(directory, results[1].task_id).run_id == results[1].run_id
    assert composition(second).children[0].run_id == results[1].run_id


@pytest.mark.parametrize("on_error", ["stop", "continue"])
def test_self_source_is_rejected_without_replacing_previous_child(tmp_path, on_error):
    snapshots = {}

    def compose(owner):
        first = owner.run_task("demo", x=1, y=2)
        directory = task_path(tmp_path, first.task_id)
        snapshots.update({path.name: path.read_bytes() for path in directory.glob("*")})
        owner.run_task("demo", x=3, y=4, source_tasks=first.task_id, on_error=on_error)

    task = parent(tmp_path, compose, input_params={"task_name": "shared"})
    if on_error == "stop":
        with pytest.raises(ChildTaskError, match="own Task ID"):
            TaskRunner().run(task)
    else:
        assert TaskRunner().run(task).state == TaskState.FAILED
    assert task.children[0].state == TaskState.SUCCEEDED
    assert task.children[1].state == TaskState.FAILED
    directory = task_path(tmp_path, task.children[0].task_id)
    assert {path.name: path.read_bytes() for path in directory.glob("*")} == snapshots


@pytest.mark.parametrize("state", [TaskState.QUEUED, TaskState.RUNNING])
def test_reused_child_name_cannot_replace_active_run(tmp_path, state):
    results = []
    first = parent(
        tmp_path,
        lambda owner: results.append(owner.run_task("demo", x=1, y=2)),
        input_params={"task_name": "research-core"},
    )
    TaskRunner().run(first)
    existing = results[0]
    directory = task_path(tmp_path, existing.task_id)
    status = read_task_metadata(directory, existing.task_id).model_copy(update={"state": state})
    write_task_metadata(directory, status)
    before = (directory / "metadata.json").read_bytes()
    task = parent(
        tmp_path,
        lambda owner: owner.run_task("demo", x=3, y=4),
        input_params={"task_name": "research-core"},
    )
    with pytest.raises(ChildTaskError, match="already exists"):
        TaskRunner().run(task)
    assert read_task_metadata(directory, existing.task_id) == status
    assert (directory / "metadata.json").read_bytes() == before


def test_child_environment_never_borrows_parent_worker_identity(tmp_path, monkeypatch):
    monkeypatch.setenv("AXONX_TASK_ID", "base#composite#worker")
    monkeypatch.setenv("AXONX_TASK_RUN_ID", "worker-run")
    monkeypatch.setenv("AXONX_TASK_CREATED_AT", "invalid-parent-timestamp")
    results = []
    task = parent(tmp_path, lambda owner: results.append(owner.run_task("demo", x=1, y=2)))
    TaskRunner().run(task)
    assert results[0].task_id != "base#composite#worker"
    assert results[0].run_id != "worker-run"


@pytest.mark.parametrize("failure_point", ["composition", "initial_status", "persistent_status"])
@pytest.mark.parametrize("on_error", ["stop", "continue"])
def test_child_startup_failure_settles_owned_status_and_closes_resources(
    tmp_path, monkeypatch, failure_point, on_error
):
    events = []

    class ResourceTask(BaseTask):
        def build_task_steps(self):
            yield self.work

        def work(self):
            events.append("work")

        def close(self):
            events.append("close")

        def build_output_params(self):
            return BaseOutputParams()

    monkeypatch.setattr(
        "axonx.task.catalog.resolver.resolve_task",
        lambda name: ResourceTask if name == "resource" else DemoTask,
    )

    def compose(owner):
        owner.run_task("resource", on_error=on_error)
        owner.run_task("demo", x=1, y=2)

    task = parent(tmp_path, compose)
    write_record = task.persist_metadata
    failed = False

    def flaky_composition():
        nonlocal failed
        if task.children and task.children[0].task_id is not None and not failed:
            if failure_point == "composition":
                failed = True
                raise OSError("startup write failed")
        write_record()

    def flaky_status(directory, status):
        nonlocal failed
        if status.reg_name == "resource" and (
            failure_point == "persistent_status" or failure_point == "initial_status" and not failed
        ):
            failed = True
            raise OSError("startup write failed")
        write_task_metadata(directory, status)

    monkeypatch.setattr(task, "persist_metadata", flaky_composition)
    monkeypatch.setattr("axonx.task.runtime.runner.write_task_metadata", flaky_status)
    if on_error == "stop":
        with pytest.raises(ChildTaskError, match="startup write failed"):
            TaskRunner().run(task)
    else:
        assert TaskRunner().run(task).state == TaskState.FAILED
        assert task.children[1].state == TaskState.SUCCEEDED

    assert failed
    assert events == ["close"]
    child = task.children[0]
    status = read_task_metadata(task_path(tmp_path, child.task_id), child.task_id)
    assert child.state == TaskState.FAILED
    if failure_point in {"composition", "persistent_status"}:
        assert status is None
    else:
        assert status.state == child.state == TaskState.FAILED
        assert status.run_id == child.run_id
        assert status.exit_code == child.exit_code == 1
        assert status.error == child.error == "OSError: startup write failed"
        assert status.finished_at is not None
    assert composition(task).children == list(task.children)


@pytest.mark.parametrize("interruption", [KeyboardInterrupt, SystemExit])
def test_continue_does_not_swallow_interrupts_and_child_resources_close(tmp_path, monkeypatch, interruption):
    events = []

    class InterruptedTask(BaseTask):
        def build_task_steps(self):
            yield self.interrupt

        def interrupt(self):
            events.append("work")
            raise interruption("stop")

        def close(self):
            events.append("close")

        def build_output_params(self):
            return BaseOutputParams()

    monkeypatch.setattr("axonx.task.catalog.resolver.resolve_task", lambda _name: InterruptedTask)

    def compose(task):
        task.run_task("interrupt", on_error="continue")
        events.append("later")

    task = parent(tmp_path, compose)
    with pytest.raises(interruption):
        TaskRunner().run(task)
    assert events == ["work", "close"]
    assert task.children[0].state == TaskState.FAILED


def test_invalid_runtime_options_and_calls_outside_runner_do_not_start_children(
    tmp_path,
):
    task = parent(tmp_path, lambda _owner: None)
    with pytest.raises(RuntimeError, match="parent TaskRunner"):
        task.run_task("demo", x=1, y=2)

    def compose(owner):
        for options in (
            {"on_error": "invalid"},
            {"task_name": "chosen"},
            {"node_name": "../escape"},
        ):
            with pytest.raises(ValueError):
                owner.run_task("demo", x=1, y=2, **options)

    task = parent(tmp_path, compose)
    assert TaskRunner().run(task).state == TaskState.SUCCEEDED
    assert composition(task).children == []


def test_result_and_children_snapshots_do_not_mutate_runtime(tmp_path):
    def compose(task):
        result = task.run_task("demo", x=1, y=2)
        result.record.state = TaskState.FAILED
        task.children[0].state = TaskState.FAILED

    task = parent(tmp_path, compose)
    assert TaskRunner().run(task).state == TaskState.SUCCEEDED
    assert composition(task).children[0].state == TaskState.SUCCEEDED


def test_custom_typed_parent_output_preserves_failed_child_aggregation(tmp_path):
    class Output(BaseOutputParams):
        total: int

    class CustomComposite(Composite):
        output_cls = Output

        def build_output_params(self):
            return self.output_cls(total=42)

    task = CustomComposite(
        {},
        workspace_path=tmp_path,
        reg_name="custom",
        compose=lambda owner: owner.run_task("demo", x=1, y=2, fail=True, on_error="continue"),
    )
    status = TaskRunner().run(task)
    assert isinstance(task.output_params, Output)
    assert status.output_params["total"] == 42
    assert status.state == TaskState.FAILED


@pytest.mark.parametrize("failed", [False, True])
def test_nested_composite_propagates_output_and_failure(tmp_path, monkeypatch, failed):
    class Nested(BaseCompositeTask):
        def build_task_steps(self):
            yield self.execute_child

        def execute_child(self):
            self.run_task("demo", x=1, y=2, fail=failed, on_error="continue")

    monkeypatch.setattr(
        "axonx.task.catalog.resolver.resolve_task",
        lambda name: Nested if name == "nested" else DemoTask,
    )
    results = []

    def compose(owner):
        results.append(owner.run_task("nested", on_error="continue"))
        results.append(owner.run_task("demo", x=3, y=4))

    task = parent(tmp_path, compose)
    status = TaskRunner().run(task)
    expected = TaskState.FAILED if failed else TaskState.SUCCEEDED
    assert status.state == expected
    assert results[0].record.state == expected
    assert results[1].success
    nested_record = read_task_metadata(task_path(tmp_path, results[0].task_id), results[0].task_id)
    assert nested_record.children[0].state == expected
    assert nested_record.children[0].task_id == "base#demo#" + task.input_params.task_name


@pytest.mark.parametrize("language", ["en", "zh"])
def test_documented_plugin_example_resolves_and_executes_through_command_entry(tmp_path, monkeypatch, language):
    guide = Path(__file__).resolve().parents[2] / "docs" / language / "guides" / "composite-tasks.md"
    code = re.search(r"```python\n(.*?)\n```", guide.read_text(), re.DOTALL).group(1)
    namespace = {"__name__": __name__}
    exec(compile(code, str(guide), "exec"), namespace)  # pylint: disable=exec-used
    monkeypatch.setattr(
        sys.modules[__name__],
        "DemoChainTask",
        namespace["DemoChainTask"],
        raising=False,
    )
    plugin = PluginInfo(
        distribution="composite-example",
        version="1",
        tasks={"demo_chain": f"{__name__}:DemoChainTask"},
    )
    monkeypatch.setattr("axonx.task.catalog.resolver.list_installed_plugins", lambda: [plugin])

    definition = get_task_definition("demo_chain")
    assert definition.source == "plugin"
    assert "children" not in definition.output_schema["properties"]
    execution = TaskCommandExecutor(tmp_path).execute(
        SimpleNamespace(
            action="exec",
            arguments={"task": "demo_chain", "x": 2, "y": 3, "doubles": 2},
        )
    )
    assert execution.status.state == TaskState.SUCCEEDED
    assert execution.output["total"] == 20
    assert len(execution.status.children) == 3


@pytest.fixture
def manager(tmp_path):
    context = SimpleNamespace(app_config=SimpleNamespace(workspace_dir=str(tmp_path)))
    instance = object.__new__(LocalTaskManager)
    instance.app_context = context
    instance._lock = asyncio.Lock()
    instance.repository = LocalTaskRepository(app_context=context)
    return instance


def save_status(tmp_path, name, *, state=TaskState.RUNNING, run_id="run", pid=123):
    status = TaskMetadata(
        version=1,
        task_id=f"base#{name}#test",
        run_id=run_id,
        task_type=TaskType.BASE,
        state=state,
        pid=pid,
    )
    directory = task_path(tmp_path, status.task_id)
    directory.mkdir(parents=True)
    write_task_metadata(directory, status)
    return status


def link_children(tmp_path, owner, *children):
    owner.children = [
        ChildTaskRecord(
            node_name=str(index),
            attempt=1,
            task=child.reg_name or "demo",
            task_id=child.task_id,
            run_id=child.run_id,
            state=child.state,
        )
        for index, child in enumerate(children)
    ]
    write_task_metadata(task_path(tmp_path, owner.task_id), owner)


@pytest.mark.parametrize("state,code", [(TaskState.CANCELLED, 130), (TaskState.FAILED, 9)])
async def test_settlement_updates_nested_children_preserving_success_and_foreign_runs(tmp_path, manager, state, code):
    root = save_status(tmp_path, "root")
    nested = save_status(tmp_path, "nested")
    leaf = save_status(tmp_path, "leaf")
    success = save_status(tmp_path, "success", state=TaskState.SUCCEEDED)
    foreign = save_status(tmp_path, "foreign", pid=456)
    replaced = save_status(tmp_path, "replaced", run_id="old")
    link_children(tmp_path, nested, leaf)
    link_children(tmp_path, root, nested, success, foreign, replaced)
    write_task_metadata(
        task_path(tmp_path, replaced.task_id),
        replaced.model_copy(update={"run_id": "new"}),
    )

    await manager._finish(root, state, code, "worker stopped")

    for status in (root, nested, leaf):
        current = await manager.get_status(status.task_id)
        assert current.state == state
        assert current.exit_code == code
    assert read_task_metadata(task_path(tmp_path, success.task_id), success.task_id).state == TaskState.SUCCEEDED
    assert read_task_metadata(task_path(tmp_path, foreign.task_id), foreign.task_id).state == TaskState.RUNNING
    replacement = read_task_metadata(task_path(tmp_path, replaced.task_id), replaced.task_id)
    assert replacement.run_id == "new" and replacement.state == TaskState.RUNNING
    assert read_task_metadata(task_path(tmp_path, root.task_id), root.task_id).children[0].state == state


async def test_worker_exit_fails_children_without_touching_replacement_parent(tmp_path, manager):
    root = save_status(tmp_path, "root")
    child = save_status(tmp_path, "child")
    link_children(tmp_path, root, child)
    await manager._handle_worker_exit(WorkerExit(-9, "", root.task_id, "stale"))
    assert read_task_metadata(task_path(tmp_path, child.task_id), child.task_id).state == TaskState.RUNNING
    await manager._handle_worker_exit(WorkerExit(-9, "", root.task_id, root.run_id))
    assert (await manager.get_status(child.task_id)).state == TaskState.FAILED


@pytest.mark.parametrize("bad_record", ["corrupt", "stale", "symlink", "directory", "fifo"])
async def test_worker_exit_ignores_invalid_or_stale_metadata(tmp_path, manager, monkeypatch, bad_record):
    root = save_status(tmp_path, "root")
    child = save_status(tmp_path, "child")
    link_children(tmp_path, root, child)
    path = task_path(tmp_path, root.task_id) / METADATA_FILE
    if bad_record == "corrupt":
        path.write_text("{")
    elif bad_record == "stale":
        data = json.loads(path.read_text())
        data["run_id"] = "stale"
        path.write_text(json.dumps(data))
    elif bad_record == "symlink":
        target = tmp_path / "external.json"
        path.rename(target)
        path.symlink_to(target)
    else:
        path.unlink()
        if bad_record == "directory":
            path.mkdir()
        else:
            os.mkfifo(path)
            read_text = Mock(wraps=Path.read_text)

            def refuse_fifo_read(current, *args, **kwargs):
                assert current != path, "Reading a composition FIFO would block settlement"
                return read_text(current, *args, **kwargs)

            monkeypatch.setattr(Path, "read_text", refuse_fifo_read)
    await manager._handle_worker_exit(WorkerExit(-9, "", root.task_id, root.run_id))
    assert read_task_metadata(task_path(tmp_path, root.task_id), root.task_id) is None or bad_record == "stale"
    assert read_task_metadata(task_path(tmp_path, child.task_id), child.task_id).state == TaskState.RUNNING


@pytest.mark.parametrize("operation", ["lstat", "read_text"])
async def test_worker_exit_retries_transient_metadata_io_failure(tmp_path, manager, monkeypatch, operation):
    root = save_status(tmp_path, "root")
    child = save_status(tmp_path, "child")
    link_children(tmp_path, root, child)
    target = task_path(tmp_path, root.task_id) / METADATA_FILE
    original = getattr(Path, operation)
    attempts = 0

    def flaky_read(path, *args, **kwargs):
        nonlocal attempts
        if path == target:
            attempts += 1
            if attempts == 1:
                raise OSError("temporary composition I/O failure")
        return original(path, *args, **kwargs)

    async def wait():
        return 9

    monkeypatch.setattr(Path, operation, flaky_read)
    monkeypatch.setattr("axonx.components.task_manager.local.supervisor.EXIT_RETRY_SECONDS", 0)
    supervisor = TaskProcessSupervisor(0, Mock(), manager._handle_worker_exit)
    process = SimpleNamespace(pid=root.pid, stderr=None, returncode=9, wait=wait)
    await supervisor._monitor(process, root.task_id, "root", root.run_id)

    assert attempts >= 2
    supervisor.logger.exception.assert_called_once()
    for status in (root, child):
        current = await manager.get_status(status.task_id)
        assert current.state == TaskState.FAILED
        assert current.exit_code == 9


WORKER_SCRIPT = """
import os
import time
from pathlib import Path
import axonx.task.catalog.resolver as resolver
from axonx.task import BaseCompositeTask, BaseOutputParams, BaseTask
from axonx.task.builtins.demo import DemoTaskInputParams
from axonx.enums import TaskType
from axonx.task.runtime.runner import TaskRunner

class Hold(BaseTask):
    def build_task_steps(self):
        yield self.hold
    def hold(self):
        (self.workspace_path / "ready").write_text(self.task_id)
        while True:
            time.sleep(1)
    def build_output_params(self):
        return BaseOutputParams()

class Inner(BaseCompositeTask):
    def build_task_steps(self):
        yield self.child
    def child(self):
        self.run_task("hold")

class Outer(BaseCompositeTask):
    # The manager submits the native base/demo definition in this fixture.
    task_type = TaskType.BASE
    input_cls = DemoTaskInputParams
    def build_task_steps(self):
        yield self.child
    def child(self):
        self.run_task("inner")

resolver.resolve_task = lambda name: {"hold": Hold, "inner": Inner}[name]
task = Outer(
    {"task_name": os.environ["AXONX_TASK_ID"].split("#")[-1], "x": 1, "y": 2},
    workspace_path=os.environ["AXONX_TASK_WORKSPACE_DIR"],
    reg_name="demo", run_id=os.environ["AXONX_TASK_RUN_ID"],
)
TaskRunner().run(task)
"""


@pytest.mark.parametrize("stop", ["cancel", "shutdown", "crash"])
async def test_real_worker_stop_settles_active_nested_children(tmp_path, monkeypatch, stop):
    script = tmp_path / "worker.py"
    script.write_text(WORKER_SCRIPT)
    create_process = asyncio.create_subprocess_exec

    async def spawn(*_args, **kwargs):
        return await create_process(sys.executable, str(script), **kwargs)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    app = Application(
        workspace_dir=str(tmp_path),
        log_dir=str(tmp_path / "logs"),
        enable_logo=False,
        log_to_console=False,
        log_to_file=False,
        components={
            "task_repository": {"default": {"backend": "local", "force_polling": True}},
            "task_manager": {"default": {"backend": "local", "terminate_grace_seconds": 0.1}},
        },
    )
    await app.start()
    try:
        instance = app.context.components["task_manager"]["default"]
        handle = await instance.submit(["--task", "demo", "--task-name", "parent", "--x", "1", "--y", "2"])
        async with asyncio.timeout(15):
            while not (tmp_path / "ready").is_file():
                await asyncio.sleep(0.02)
        root_record = read_task_metadata(task_path(tmp_path, handle.task_id), handle.task_id)
        nested = root_record.children[0]
        leaf_id = (tmp_path / "ready").read_text()
        if stop == "cancel":
            assert await instance.cancel(handle.task_id, handle.run_id)
        elif stop == "shutdown":
            await app.close()
        else:
            pid = instance._supervisor.run_pids[handle.run_id]
            os.kill(pid, 9)
            async with asyncio.timeout(10):
                while not read_task_metadata(task_path(tmp_path, handle.task_id), handle.task_id).state.is_terminal:
                    await asyncio.sleep(0.02)
        expected = TaskState.FAILED if stop == "crash" else TaskState.CANCELLED
        for task_id in (handle.task_id, nested.task_id, leaf_id):
            assert read_task_metadata(task_path(tmp_path, task_id), task_id).state == expected
        assert read_task_metadata(task_path(tmp_path, handle.task_id), handle.task_id).children[0].state == expected
    finally:
        await app.close()


@pytest.mark.parametrize("kind", ["file", "symlink"])
def test_rerun_rejects_invalid_persistent_storage_before_clearing_outputs(tmp_path, kind):
    task = parent(tmp_path, lambda task: None, input_params={"task_name": "named"})
    TaskRunner().run(task)
    before = (task.task_dir / "metadata.json").read_bytes()
    persistent = task.persistent_dir
    if kind == "file":
        persistent.write_text("invalid")
    else:
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "keep.txt").write_text("keep")
        persistent.symlink_to(outside, target_is_directory=True)
    replacement = parent(tmp_path, lambda task: None, input_params={"task_name": "named"})
    with pytest.raises(ValueError, match="Persistent Task storage"):
        TaskRunner().run(replacement)
    assert (task.task_dir / "metadata.json").read_bytes() == before
    if kind == "symlink":
        assert (outside / "keep.txt").read_text() == "keep"
