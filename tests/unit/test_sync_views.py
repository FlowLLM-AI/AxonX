"""Workflow timing, model isolation through logical invocation names and atomic display-view replacement."""

import asyncio
import shutil
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import Field

from axonx.app.components.sync.applier import TaskArchiveApplier, snapshot_index
from axonx.app.components.sync.archive import build_archive
from axonx.app.components.sync.artifacts import plan_task
from axonx.app.components.sync.models import SnapshotChangedError
from axonx.app.components.sync.replica import prepare_group, task_group
from axonx.app.core.application import Application
from axonx.task.core.base import BaseTask
from axonx.task.models.identity import TaskState
from axonx.task.models.params import BaseInputParams, BaseOutputParams
from axonx.task.runtime.executor import TaskExecutor
from axonx.task.storage.artifacts import artifact_record
from axonx.task.storage.logs import TaskLogReader
from axonx.task.storage.workspace import read_entry, task_path, write_task_metadata
from axonx.utils.logging import LoggingConfig, configure_logging

BUDGET = 8_000_000


class Inputs(BaseInputParams):
    models: dict = Field(default_factory=dict)


class BranchInput(BaseInputParams):
    model: dict = Field(default_factory=dict)


class Outputs(BaseOutputParams):
    models: dict


class Branch(BaseTask):
    input_cls = BranchInput

    def build_task_steps(self):
        yield self.publish

    def publish(self):
        model = self.input_params.model.get("task_name", self.input_params.task_name)
        self.logger.info("private publication for {}", model)
        (self.task_dir / "result.txt").write_text(model)

    def build_output_params(self):
        return BaseOutputParams(artifacts={"result": artifact_record(self.task_dir / "result.txt", self.task_dir)})


class Nested(Branch):
    def publish(self):
        super().publish()
        self.run_task("leaf", task_name=self.input_params.task_name + "-window", model=self.input_params.model)


class Workflow(BaseTask):
    input_cls = Inputs
    output_cls = Outputs
    models: dict

    def build_task_steps(self):
        yield self.run

    def run(self):
        self.models = {}
        self.run_task("leaf", task_name="market-input", node_name="leaf")
        for slot, models in self.input_params.models.items():
            self.models[slot] = {}
            for model in models:
                name = model["task_name"]
                self.report_progress(name=f"history:{name}-{slot}", group="history", state="running")
                child = self.run_task(
                    "branch", task_name=f"h-{slot}-{len(self.children)}", node_name=f"{name}-{slot}-branch", model=model
                )
                self.models[slot][name] = {"status": "done", "stages": {"branch": child.child_task_id}}
                self.report_progress(name=f"history:{name}-{slot}", state="done")
        self.logger.info("mixed parent log: axon-v1 and axon2-0945")

    def build_output_params(self):
        return Outputs(models=self.models)


@pytest.fixture
def workflow(tmp_path):
    configure_logging(LoggingConfig(log_dir=tmp_path / "logs", log_to_console=False))
    source = tmp_path / "source"
    task = Workflow(
        {
            "task_name": "combined",
            "models": {
                "0945": [{"task_name": "axon2-0945"}],
                "1445": [{"task_name": "axon-v1"}],
            },
        },
        workspace_path=source,
        reg_name="workflow",
    )
    status = TaskExecutor(resolve_task=lambda name: Nested if name == "branch" else Branch).execute(task)
    assert status.state == TaskState.SUCCEEDED
    return source, status


def send(source, status, target, tmp_path, patterns=(), when="live"):
    plans = prepare_group(
        source,
        status.task_id,
        tmp_path / "prepared",
        BUDGET,
        TaskLogReader(source),
        snapshot_index(target),
        model_names=patterns,
        when=when,
    )
    if plans:
        archive = tmp_path / "group.tar.gz"
        build_archive(plans, archive)
        return TaskArchiveApplier(target, BUDGET).apply(archive, [])
    return None


@pytest.mark.parametrize("model,excluded", [("axon-v1", "axon2-0945"), ("axon2-*", "axon-v1")])
@pytest.mark.parametrize("when", ["live", "terminal"])
def test_model_views_roundtrip_without_foreign_parameters_results_steps_or_logs(
    workflow, tmp_path, model, excluded, when
):
    source, status = workflow
    target = tmp_path / "target"
    original = (task_path(source, status.task_id) / "metadata.json").read_bytes()
    applied = send(source, status, target, tmp_path, (model,), when)
    assert applied.applied
    parent = read_entry(target, status.task_id)
    assert len(parent.children) == 2  # The model branch and shared market-input Task.
    assert parent.log_path == "" and parent.replica.log is None
    assert parent.replica.snapshot.when == when
    all_text = "\n".join(path.read_text() for path in target.glob("tasks/**/*") if path.is_file())
    assert excluded not in all_text
    assert "mixed parent log" not in all_text
    assert (task_path(source, status.task_id) / "metadata.json").read_bytes() == original
    assert len(snapshot_index(target, frozenset({status.task_id}))) == 4
    assert send(source, status, target, tmp_path, (model,), when) is None


def test_excluded_restarted_branch_does_not_block_the_selected_model(workflow, tmp_path):
    source, status = workflow
    target = tmp_path / "target"
    send(source, status, target, tmp_path, ("axon2-*",))
    native = next(child for child in status.children if child.node_name.startswith("axon2-0945-"))
    metadata = read_entry(source, native.child_task_id)
    metadata.started_at += timedelta(seconds=1)
    write_task_metadata(task_path(source, native.child_task_id), metadata)
    assert task_group(source, status.task_id, ("axon-v1",))
    group = task_group(source, status.task_id, ("axon2-*",))
    assert native.child_task_id not in group
    assert all(child.child_task_id != native.child_task_id for child in group[status.task_id].children)
    # Source invocation history stays intact; a replica contains only available runs.
    assert read_entry(source, status.task_id).children == status.children
    send(source, status, target, tmp_path, ("axon2-*",))
    assert read_entry(target, status.task_id).output_params["models"]["0945"]["axon2-0945"]["status"] == "done"


def test_changing_a_view_removes_only_obsolete_owned_replicas(workflow, tmp_path):
    source, status = workflow
    target = tmp_path / "target"
    send(source, status, target, tmp_path)
    previous = set(snapshot_index(target))
    applied = send(source, status, target, tmp_path, ("axon-v1",))
    assert applied.deleted
    assert len(previous - set(snapshot_index(target))) == 2
    assert all(read_entry(target, identity).replica is not None for identity in snapshot_index(target))


@pytest.mark.parametrize("when", ["live", "terminal"])
def test_flush_waits_for_the_workflow_and_retries_through_the_same_queue(workflow, tmp_path, monkeypatch, when):
    source, status = workflow
    status.state, status.finished_at = TaskState.RUNNING, None
    write_task_metadata(task_path(source, status.task_id), status)
    target = tmp_path / "target"
    applier = TaskArchiveApplier(target, BUDGET)
    failing = [False]

    class Receiver:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        async def run_job(self, name, arguments):
            if name == "task_sync_index":
                return SimpleNamespace(
                    success=True,
                    answer={
                        "transfer_budget_bytes": BUDGET,
                        "tasks": snapshot_index(target, frozenset(arguments["root_task_ids"])),
                    },
                )
            if failing[0]:
                return SimpleNamespace(success=False, answer="temporary receiver failure")
            return SimpleNamespace(success=True, answer=applier.apply(Path(arguments["path"]), []))

        async def copy_file(self, path, **_):
            return SimpleNamespace(path=str(path), size=path.stat().st_size)

        async def discard_file(self, _path):
            pass

    app = Application(
        workspace_dir=str(source),
        log_to_console=False,
        log_to_file=False,
        targets=[{"address": "http://receiver:1024"}],
        components={
            "task_index": {"default": {"backend": "local"}},
            "sync": {
                "selected": {
                    "backend": "local",
                    "target": "http://receiver:1024",
                    "model_names": ["axon-v1"],
                    "rules": {"workflow": when},
                }
            },
        },
    )
    component = app.context.components["sync"]["selected"]
    monkeypatch.setattr(component, "_client", Receiver)

    async def run():
        first = await component.flush()
        assert bool(first.uploaded) == (when == "live")
        status.state = TaskState.SUCCEEDED
        write_task_metadata(task_path(source, status.task_id), status)
        component._on_change(frozenset({status.task_id}))
        failing[0] = True
        failed = await component.flush()
        assert failed.deferred
        failing[0] = False
        assert (await component.flush()).uploaded
        assert not (await component.flush()).uploaded
        parent = read_entry(target, status.task_id)
        missing = parent.children[-1].child_task_id
        shutil.rmtree(task_path(target, missing))
        assert not snapshot_index(target)
        assert (await component.flush()).uploaded
        assert read_entry(target, missing) is not None

    asyncio.run(run())


def test_terminal_group_does_not_publish_completed_children_while_parent_runs(workflow, tmp_path):
    source, status = workflow
    status.state, status.finished_at = TaskState.RUNNING, None
    write_task_metadata(task_path(source, status.task_id), status)
    with pytest.raises(SnapshotChangedError, match="not completed"):
        prepare_group(source, status.task_id, tmp_path / "prepared", BUDGET, TaskLogReader(source), {}, when="terminal")


def test_terminal_failure_publishes_only_the_selected_model_error(workflow, tmp_path):
    source, status = workflow
    status.state, status.exit_code = TaskState.FAILED, 1
    status.error = "axon2-0945 private failure"
    status.output_params["models"]["0945"]["axon2-0945"].update(error=status.error)
    write_task_metadata(task_path(source, status.task_id), status)
    target = tmp_path / "target"
    assert send(source, status, target, tmp_path, ("axon-v1",), "terminal").applied
    parent = read_entry(target, status.task_id)
    assert parent.state == TaskState.FAILED
    assert parent.error == "Task exited with code 1"
    assert "private failure" not in parent.model_dump_json()


def test_single_model_root_uses_its_name_and_includes_all_descendants(tmp_path):
    source = tmp_path / "source"
    task = Nested({"task_name": "axon-v1"}, workspace_path=source, reg_name="v1_research")
    status = TaskExecutor(resolve_task=lambda _: Branch).execute(task)
    status.input_params["train"] = {"task_name": ""}
    write_task_metadata(task_path(source, status.task_id), status)
    assert len(task_group(source, status.task_id, ("axon-v1",))) == 2
    assert not task_group(source, status.task_id, ("axon2-*",))


def test_terminal_policy_retains_published_model_artifacts(workflow):
    source, status = workflow
    branch = next(child for child in status.children if child.node_name.startswith("axon-v1-"))
    child = read_entry(source, branch.child_task_id)
    directory = task_path(source, child.task_id)
    (directory / "weights.bin").write_bytes(b"published weights")
    child.output_params["artifacts"]["model_weights"] = artifact_record(directory / "weights.bin", directory)
    write_task_metadata(directory, child)
    assert "weights.bin" not in {item.relative for item in plan_task(source, child.task_id, snapshot=child).files}
    assert "weights.bin" in {
        item.relative for item in plan_task(source, child.task_id, snapshot=child, live=False).files
    }


def test_model_nodes_match_exactly_even_when_names_overlap(tmp_path):
    source = tmp_path / "source"
    task = Workflow(
        {"models": {"0945": [{"task_name": "model"}, {"task_name": "model-0945"}]}},
        workspace_path=source,
        reg_name="workflow",
    )
    status = TaskExecutor(resolve_task=lambda _: Branch).execute(task)
    assert status.state == TaskState.SUCCEEDED
    for model in ("model", "model-0945"):
        group = task_group(source, task.task_id, (model,))
        assert set(group[task.task_id].output_params["models"]["0945"]) == {model}
        assert {child.node_name for child in group[task.task_id].children} == {"leaf", f"{model}-0945-branch"}


def test_partial_view_rejects_unrecognized_logical_child_nodes(workflow):
    source, status = workflow
    status.children[-1].node_name = "opaque-node"
    write_task_metadata(task_path(source, status.task_id), status)
    with pytest.raises(SnapshotChangedError, match="no model node name"):
        task_group(source, status.task_id, ("axon-v1",))
