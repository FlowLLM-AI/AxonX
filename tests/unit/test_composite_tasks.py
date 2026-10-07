"""Composite Tasks preserve child contracts, ownership, and failure semantics."""

import asyncio
import json
import os
import re
import sys
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest

from axonx.components.task_manager.local.manager import LocalTaskManager
from axonx.components.task_manager.local.supervisor import WorkerExit
from axonx.components.task_repository import LocalTaskRepository
from axonx.core import Application
from axonx.enums import TaskState, TaskType
from axonx.plugin_kit.models import PluginInfo
from axonx.task import BaseCompositeOutputParams, BaseCompositeTask, BaseOutputParams, BaseTask, ChildTaskError
from axonx.task.builtins.demo import DemoTask, DemoTaskOutputParams
from axonx.task.catalog import get_task_definition
from axonx.task.runtime.executor import TaskCommandExecutor
from axonx.task.runtime.runner import TaskRunner
from axonx.task.storage.artifacts import artifact_path
from axonx.task.storage.composition import (
    COMPOSITION_FILE,
    ChildTaskRecord,
    TaskComposition,
    read_composition,
    write_composition,
)
from axonx.task.storage.workspace import TaskStatus, read_status, task_path, write_status


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
    return read_composition(task.task_dir, task.task_id, task.context.run_id)


def test_sequence_loops_output_binding_and_explicit_lineage(tmp_path):
    results = []

    def compose(task):
        first = task.run_task("demo", node_name="sum", x=2, y=3)
        assert isinstance(first.output_params, DemoTaskOutputParams)
        for index in range(3):
            results.append(
                task.run_task(
                    "demo", node_name=f"feature-{index}", x=first.output["result"], y=index, source_tasks=first.task_id
                )
            )
        # Keep the stage barrier: every feature exists before predictions begin.
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
        child_status = read_status(directory, child.task_id)
        assert child_status.state == TaskState.SUCCEEDED
        assert child_status.pid == os.getpid()
        assert child_status.run_id == child.run_id != task.context.run_id
        assert (directory / "metadata.json").is_file()
    first_status = read_status(task_path(tmp_path, task.children[0].task_id), task.children[0].task_id)
    feature_status = read_status(task_path(tmp_path, results[0].task_id), results[0].task_id)
    assert first_status.config["source_tasks"] == ""
    assert feature_status.config["source_tasks"] == task.children[0].task_id
    metadata = json.loads(task.metadata_path.read_text())
    assert artifact_path(task.task_dir, metadata, "composition") == task.task_dir / COMPOSITION_FILE
    assert composition(task).children == list(task.children)


def test_fail_fast_retains_failed_child_and_skips_later_work(tmp_path):
    def compose(task):
        task.run_task("demo", x=1, y=2, fail=True)
        task.run_task("demo", x=3, y=4)

    task = parent(tmp_path, compose)
    with pytest.raises(ChildTaskError, match="Demo failure requested") as failure:
        TaskRunner().run(task)

    assert failure.value.result.success is False
    assert failure.value.result.task_id == task.children[0].task_id
    assert read_status(task.task_dir, task.task_id).state == TaskState.FAILED
    assert len(composition(task).children) == 1
    assert task.children[0].state == TaskState.FAILED
    assert (
        read_status(task_path(tmp_path, task.children[0].task_id), task.children[0].task_id).state == TaskState.FAILED
    )
    assert not task.metadata_path.exists()


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
    assert status.result["children"][0]["error"]
    assert composition(task).children[1].state == TaskState.SUCCEEDED
    assert not task.metadata_path.exists()
    if failure == "exit_code":
        assert results[0].output["result"] == 3
    else:
        with pytest.raises(RuntimeError, match="output is unavailable"):
            _ = results[0].output


def test_children_have_distinct_attempts_and_survive_named_parent_rerun(tmp_path):
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
    assert len({child.task_id for child in (*first.children, *second.children)}) == 4
    for task_id, before in snapshots.items():
        assert (task_path(tmp_path, task_id) / "metadata.json").read_bytes() == before


def test_child_environment_never_borrows_parent_worker_identity(tmp_path, monkeypatch):
    monkeypatch.setenv("AXONX_TASK_ID", "base#composite#worker")
    monkeypatch.setenv("AXONX_TASK_RUN_ID", "worker-run")
    monkeypatch.setenv("AXONX_TASK_CREATED_AT", "invalid-parent-timestamp")
    results = []
    task = parent(tmp_path, lambda owner: results.append(owner.run_task("demo", x=1, y=2)))
    TaskRunner().run(task)
    assert results[0].task_id != "base#composite#worker"
    assert results[0].run_id != "worker-run"


def test_collision_does_not_replace_existing_child(tmp_path):
    task = parent(tmp_path, lambda owner: owner.run_task("demo", node_name="sum", on_error="continue", x=1, y=2))
    identity = "\0".join((task.task_id, task.context.run_id, "sum", "1"))
    name = "c-" + sha256(identity.encode()).hexdigest()[:30]
    existing = DemoTask({"task_name": name, "x": 10, "y": 20}, workspace_path=tmp_path, reg_name="demo")
    TaskRunner().run(existing)
    before = existing.metadata_path.read_bytes()

    assert TaskRunner().run(task).state == TaskState.FAILED
    assert existing.metadata_path.read_bytes() == before
    assert "FileExistsError" in task.children[0].error


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


def test_invalid_runtime_options_and_calls_outside_runner_do_not_start_children(tmp_path):
    task = parent(tmp_path, lambda _owner: None)
    with pytest.raises(RuntimeError, match="parent TaskRunner"):
        task.run_task("demo", x=1, y=2)

    def compose(owner):
        for options in ({"on_error": "invalid"}, {"task_name": "chosen"}, {"node_name": "../escape"}):
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
    class Output(BaseCompositeOutputParams):
        total: int

    class CustomComposite(Composite):
        output_cls = Output

        def build_output_params(self):
            return self.output_cls(**self.composition_output(), total=42)

    task = CustomComposite(
        {},
        workspace_path=tmp_path,
        reg_name="custom",
        compose=lambda owner: owner.run_task("demo", x=1, y=2, fail=True, on_error="continue"),
    )
    status = TaskRunner().run(task)
    assert isinstance(task.output_params, Output)
    assert status.result["total"] == 42
    assert status.state == TaskState.FAILED


@pytest.mark.parametrize("failed", [False, True])
def test_nested_composite_propagates_output_and_failure(tmp_path, monkeypatch, failed):
    class Nested(BaseCompositeTask):
        def build_task_steps(self):
            yield self.execute_child

        def execute_child(self):
            self.run_task("demo", x=1, y=2, fail=failed, on_error="continue")

    monkeypatch.setattr(
        "axonx.task.catalog.resolver.resolve_task", lambda name: Nested if name == "nested" else DemoTask
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
    nested_record = read_composition(task_path(tmp_path, results[0].task_id), results[0].task_id, results[0].run_id)
    assert nested_record.children[0].state == expected
    assert results[0].output["children"][0]["task_id"] == nested_record.children[0].task_id


@pytest.mark.parametrize("language", ["en", "zh"])
def test_documented_plugin_example_resolves_and_executes_through_command_entry(tmp_path, monkeypatch, language):
    guide = Path(__file__).resolve().parents[2] / "docs" / language / "guides" / "composite-tasks.md"
    code = re.search(r"```python\n(.*?)\n```", guide.read_text(), re.DOTALL).group(1)
    namespace = {"__name__": __name__}
    exec(compile(code, str(guide), "exec"), namespace)  # pylint: disable=exec-used
    monkeypatch.setattr(sys.modules[__name__], "DemoChainTask", namespace["DemoChainTask"], raising=False)
    plugin = PluginInfo(
        distribution="composite-example", version="1", tasks={"demo_chain": f"{__name__}:DemoChainTask"}
    )
    monkeypatch.setattr("axonx.task.catalog.resolver.list_installed_plugins", lambda: [plugin])

    definition = get_task_definition("demo_chain")
    assert definition.source == "plugin"
    assert "children" in definition.output_schema["properties"]
    execution = TaskCommandExecutor(tmp_path).execute(
        SimpleNamespace(action="exec", arguments={"task": "demo_chain", "x": 2, "y": 3, "doubles": 2})
    )
    assert execution.status.state == TaskState.SUCCEEDED
    assert execution.output["total"] == 20
    assert len(execution.output["children"]) == 3


@pytest.fixture
def manager(tmp_path):
    context = SimpleNamespace(app_config=SimpleNamespace(workspace_dir=str(tmp_path)))
    instance = object.__new__(LocalTaskManager)
    instance.app_context = context
    instance._lock = asyncio.Lock()
    instance.repository = LocalTaskRepository(app_context=context)
    return instance


def save_status(tmp_path, name, *, state=TaskState.RUNNING, run_id="run", pid=123):
    status = TaskStatus(task_id=f"base#{name}#test", run_id=run_id, task_type=TaskType.BASE, state=state, pid=pid)
    directory = task_path(tmp_path, status.task_id)
    directory.mkdir(parents=True)
    write_status(directory, status)
    return status


def link_children(tmp_path, owner, *children):
    record = TaskComposition(
        task_id=owner.task_id,
        run_id=owner.run_id,
        children=[
            ChildTaskRecord(
                node_name=str(index),
                attempt=1,
                task=child.task_name or "demo",
                task_id=child.task_id,
                run_id=child.run_id,
                state=child.state,
            )
            for index, child in enumerate(children)
        ],
    )
    write_composition(task_path(tmp_path, owner.task_id), record)


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
    write_status(task_path(tmp_path, replaced.task_id), replaced.model_copy(update={"run_id": "new"}))

    await manager._finish(root, state, code, "worker stopped")

    for status in (root, nested, leaf):
        current = await manager.get_status(status.task_id)
        assert current.state == state
        assert current.exit_code == code
    assert read_status(task_path(tmp_path, success.task_id), success.task_id).state == TaskState.SUCCEEDED
    assert read_status(task_path(tmp_path, foreign.task_id), foreign.task_id).state == TaskState.RUNNING
    replacement = read_status(task_path(tmp_path, replaced.task_id), replaced.task_id)
    assert replacement.run_id == "new" and replacement.state == TaskState.RUNNING
    assert read_composition(task_path(tmp_path, root.task_id), root.task_id, root.run_id).children[0].state == state


async def test_worker_exit_fails_children_without_touching_replacement_parent(tmp_path, manager):
    root = save_status(tmp_path, "root")
    child = save_status(tmp_path, "child")
    link_children(tmp_path, root, child)
    await manager._handle_worker_exit(WorkerExit(-9, "", root.task_id, "stale"))
    assert read_status(task_path(tmp_path, child.task_id), child.task_id).state == TaskState.RUNNING
    await manager._handle_worker_exit(WorkerExit(-9, "", root.task_id, root.run_id))
    assert (await manager.get_status(child.task_id)).state == TaskState.FAILED


@pytest.mark.parametrize("bad_record", ["corrupt", "stale", "symlink"])
async def test_settlement_ignores_invalid_or_stale_composition(tmp_path, manager, bad_record):
    root = save_status(tmp_path, "root")
    child = save_status(tmp_path, "child")
    link_children(tmp_path, root, child)
    path = task_path(tmp_path, root.task_id) / COMPOSITION_FILE
    if bad_record == "corrupt":
        path.write_text("{")
    elif bad_record == "stale":
        data = json.loads(path.read_text())
        data["run_id"] = "stale"
        path.write_text(json.dumps(data))
    else:
        target = tmp_path / "external.json"
        path.rename(target)
        path.symlink_to(target)
    await manager._finish(root, TaskState.CANCELLED, 130, "stop")
    assert read_status(task_path(tmp_path, child.task_id), child.task_id).state == TaskState.RUNNING


WORKER_SCRIPT = """
import os
import time
from pathlib import Path
import axonx.task.catalog.resolver as resolver
from axonx.task import BaseCompositeTask, BaseOutputParams, BaseTask
from axonx.task.builtins.demo import DemoTaskInputParams
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
        root_record = read_composition(task_path(tmp_path, handle.task_id), handle.task_id, handle.run_id)
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
                while not read_status(task_path(tmp_path, handle.task_id), handle.task_id).state.is_terminal:
                    await asyncio.sleep(0.02)
        expected = TaskState.FAILED if stop == "crash" else TaskState.CANCELLED
        for task_id in (handle.task_id, nested.task_id, leaf_id):
            assert read_status(task_path(tmp_path, task_id), task_id).state == expected
        assert (
            read_composition(task_path(tmp_path, handle.task_id), handle.task_id, handle.run_id).children[0].state
            == expected
        )
    finally:
        await app.close()
