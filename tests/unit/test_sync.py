"""Verify application-owned display replica application."""

import hashlib
import os
import tarfile
from datetime import timedelta

import polars as pl
import pytest

from axonx.app.components.sync import replica as replica_module
from axonx.app.components.sync.artifacts import plan_task
from axonx.app.components.sync.local import LocalSyncComponent
from axonx.app.components.sync.models import SnapshotChangedError
from axonx.app.components.sync.replica import ReplicaBuilder, prepare_group
from axonx.app.workspace import uploads as uploads_module
from axonx.app.workspace.core import Workspace
from axonx.client.files import archive_budget, build_file_archive
from axonx.task.builtins.demo import DemoTask
from axonx.task.models.identity import TaskState
from axonx.task.runtime.executor import TaskExecutor
from axonx.task.storage.logs import TaskLogReader
from axonx.task.storage.workspace import read_entry, task_directory, task_path, write_task_metadata
from axonx.utils.logging import LoggingConfig, configure_logging


def archive_plan(task_id, plan, archive):
    build_file_archive({task_directory(task_id): plan.directory}, archive)


@pytest.fixture
def source_task(tmp_path):
    configure_logging(LoggingConfig(log_to_console=False, log_to_file=False))
    source = tmp_path / "source"
    status = TaskExecutor().execute(
        DemoTask({"task_name": "sync", "x": 1, "y": 2}, workspace_path=source, reg_name="demo")
    )
    directory = task_path(source, status.task_id)
    artifact = directory / "result.txt"
    artifact.write_text("retained publication")
    status.output_params["artifacts"] = {"result": {"path": artifact.name}}
    write_task_metadata(directory, status)
    return source, status, directory


@pytest.mark.parametrize("name", ["named", "2026102915aB3x"])
def test_task_local_logs_roundtrip_through_display_sync(tmp_path, name):
    configure_logging(LoggingConfig(log_dir=tmp_path / "logs", log_to_console=False))
    source = tmp_path / "source"
    status = TaskExecutor().execute(
        DemoTask({"task_name": name, "x": 1, "y": 2}, workspace_path=source, reg_name="demo")
    )
    content = (task_path(source, status.task_id) / status.log_path).read_text()
    prepared = task_path(tmp_path / "prepared", status.task_id)
    budget = 1_000_000
    plan = ReplicaBuilder(source, status.task_id, prepared, budget, TaskLogReader(source)).prepare()
    archive = tmp_path / "replica.tar.gz"
    archive_plan(status.task_id, plan, archive)
    target = tmp_path / "target"
    Workspace(target).uploads.replace(archive, budget)
    replica = read_entry(target, status.task_id)
    chunk = TaskLogReader(target).read_status(replica, 0)
    assert chunk.content == content
    assert chunk.next_offset == len(content.encode())
    assert replica.log_path == ""
    assert not (task_path(target, status.task_id) / "task.log").exists()


@pytest.mark.parametrize("budget", [0, -1, True, None])
def test_task_archive_budget_is_validated_before_mutation(tmp_path, budget):
    with pytest.raises(ValueError, match="positive integer"):
        Workspace(tmp_path).uploads.replace(tmp_path / "absent.tar.gz", budget)


@pytest.mark.parametrize("maximum", [0, -1, True, 1.5])
def test_archive_batch_count_must_be_a_positive_integer(maximum):
    with pytest.raises(ValueError, match="max_archives_per_flush must be a positive integer"):
        LocalSyncComponent(target="example:1024", max_archives_per_flush=maximum)


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf")])
def test_sync_timeout_must_be_finite_and_positive(timeout):
    with pytest.raises(ValueError, match="timeout_seconds must be finite and positive"):
        LocalSyncComponent(target="example:1024", timeout_seconds=timeout)


@pytest.mark.parametrize(
    "options",
    [
        {"model_names": "axon-v1"},
        {"model_names": [""]},
        {"rules": {"workflow": "sometimes"}},
        {"rules": {"not a registration": "terminal"}},
        {"rules": ["workflow"]},
        {"task_names": ["axon-v1"]},
        {"live_task_ids": ["base#workflow#combined"]},
    ],
)
def test_sync_configuration_rejects_ambiguous_or_invalid_selection(options):
    with pytest.raises((TypeError, ValueError)):
        LocalSyncComponent(target="example:1024", **options)


def test_replica_sampling_keeps_complete_days_and_preserves_the_source(tmp_path, source_task):
    source, status, directory = source_task
    artifact = directory / "features.parquet"
    days = ["20261023", "20261024", "20261025", "20261026"]
    pl.DataFrame(
        {
            "trade_date": [day for day in days for _ in range(1000)],
            "value": [hashlib.sha256(str(index).encode()).hexdigest() for index in range(4000)],
        }
    ).write_parquet(artifact)
    original = artifact.read_bytes()
    status.output_params["artifacts"] = {"features": {"path": artifact.name}}
    write_task_metadata(directory, status)

    prepared = tmp_path / "prepared"
    budget = 100_000
    plan = ReplicaBuilder(source, status.task_id, prepared, budget).prepare()
    sampled = pl.read_parquet(prepared / artifact.name)
    retained = sorted(sampled["trade_date"].unique().to_list())
    assert retained and len(retained) < len(days)
    assert retained == days[-len(retained) :]
    assert set(sampled.group_by("trade_date").len()["len"]) == {1000}
    assert plan.size <= archive_budget(budget)
    assert artifact.read_bytes() == original
    archive = tmp_path / "sample.tar.gz"
    archive_plan(status.task_id, plan, archive)
    first_archive = archive.read_bytes()
    archive_plan(status.task_id, plan, archive)
    assert archive.read_bytes() == first_archive
    target = tmp_path / "target"
    target.mkdir()
    Workspace(target).uploads.replace(archive, budget)
    replica = read_entry(target, status.task_id).replica
    assert replica.files[artifact.name].sampled
    assert replica.files[artifact.name].dates == retained


def test_changed_tasks_send_complete_directories_and_skip_unchanged_sources(tmp_path, source_task):
    source, status, directory = source_task
    budget = 1_000_000
    logs = TaskLogReader(source)
    version, plans = prepare_group(source, status.task_id, tmp_path / "first", budget, logs)
    target = tmp_path / "target"
    store = Workspace(target).uploads
    archive = tmp_path / "live.tar.gz"
    build_file_archive({name: plan.directory for name, plan in plans.items()}, archive)
    store.replace(archive, budget)
    assert prepare_group(source, status.task_id, tmp_path / "unchanged", budget, logs, version) is None
    status.output_params["progress"] = 1
    write_task_metadata(directory, status)
    changed, plans = prepare_group(source, status.task_id, tmp_path / "second", budget, logs, version)
    assert changed != version
    build_file_archive({name: plan.directory for name, plan in plans.items()}, archive)
    with tarfile.open(archive) as stream:
        assert any(member.name.endswith("/result.txt") for member in stream.getmembers())
    store.replace(archive, budget)
    assert read_entry(target, status.task_id).output_params["progress"] == 1
    assert (task_path(target, status.task_id) / "result.txt").read_text() == "retained publication"


@pytest.mark.parametrize("relative", ["../escape", "/absolute"])
def test_published_artifact_paths_cannot_escape_the_task(source_task, relative):
    source, status, directory = source_task
    status.output_params["artifacts"]["result"]["path"] = relative
    write_task_metadata(directory, status)
    with pytest.raises(ValueError, match="inside its Task"):
        plan_task(source, status.task_id)


def test_published_symlinks_are_rejected_and_unpublished_files_are_excluded(tmp_path, source_task):
    source, status, directory = source_task
    (directory / "private.txt").write_text("unpublished")
    plan = plan_task(source, status.task_id)
    assert "private.txt" not in {item.relative for item in plan.files}
    outside = tmp_path / "outside.txt"
    outside.write_text("outside")
    (directory / "result.txt").unlink()
    (directory / "result.txt").symlink_to(outside)
    with pytest.raises(ValueError, match="Invalid replica path"):
        plan_task(source, status.task_id)


def test_live_window_files_are_included_without_waiting_for_parent_completion(source_task):
    source, status, directory = source_task
    pl.DataFrame({"ts_code": ["A"], "open": [10]}).write_parquet(directory / "snapshot_data.parquet")
    (directory / "snapshot_quality.parquet").write_bytes(b"details")
    (directory / "unpublished_data.parquet").write_text("partial")
    status.state = TaskState.RUNNING
    status.output_params = {
        "windows": [
            {
                "key": "snapshot",
                "status": "done",
                "artifacts": {
                    "data": {"path": "snapshot_data.parquet"},
                    "quality_details": {"path": "snapshot_quality.parquet"},
                },
            }
        ]
    }
    plan = plan_task(source, status.task_id, snapshot=status)
    assert {item.relative for item in plan.files} == {
        "metadata.json",
        "events.jsonl",
        "snapshot_data.parquet",
        "snapshot_quality.parquet",
    }


def test_commit_failure_restores_the_previous_replica(tmp_path, source_task, monkeypatch):
    source, status, directory = source_task
    budget = 1_000_000
    target = tmp_path / "target"
    target.mkdir()
    receiver = Workspace(target).uploads
    archive = tmp_path / "replica.tar.gz"
    first = ReplicaBuilder(source, status.task_id, tmp_path / "first", budget).prepare()
    archive_plan(status.task_id, first, archive)
    receiver.replace(archive, budget)
    destination = task_path(target, status.task_id)
    before = {path.name: path.read_bytes() for path in destination.iterdir() if path.is_file()}
    (directory / "result.txt").write_text("new publication")
    second = ReplicaBuilder(source, status.task_id, tmp_path / "second", budget).prepare()
    archive_plan(status.task_id, second, archive)
    replace = os.replace

    def fail_install(incoming, final):
        if "incoming" in incoming.parts and final == destination:
            raise OSError("commit failed")
        return replace(incoming, final)

    monkeypatch.setattr(uploads_module.os, "replace", fail_install)
    with pytest.raises(OSError, match="commit failed"):
        receiver.replace(archive, budget)
    assert {path.name: path.read_bytes() for path in destination.iterdir() if path.is_file()} == before


def test_source_restart_during_capture_is_rejected(tmp_path, source_task, monkeypatch):
    source, status, directory = source_task
    write = replica_module.write_task_metadata

    def restart_after_capture(destination, metadata):
        write(destination, metadata)
        status.started_at += timedelta(seconds=1)
        write(directory, status)

    monkeypatch.setattr(replica_module, "write_task_metadata", restart_after_capture)
    with pytest.raises(SnapshotChangedError, match="restarted"):
        prepare_group(source, status.task_id, tmp_path / "prepared", 1_000_000, TaskLogReader(source))
    assert status.replica is None


def test_live_training_sync_uses_registry_to_exclude_model_weights(source_task):
    source, status, directory = source_task
    model = directory / "models" / "mlp_seed_42_fit_end_20230101.pt"
    model.parent.mkdir()
    model.write_bytes(b"final weights")
    name = model.stem
    status.output_params = {
        "models": {name: {"model_artifact": name, "training_curve": {"x": ["1"]}}},
        "artifacts": {name: {"path": model.relative_to(directory).as_posix()}},
    }
    write_task_metadata(directory, status)
    assert model.relative_to(directory).as_posix() in {
        item.relative for item in plan_task(source, status.task_id).files
    }
    assert model.relative_to(directory).as_posix() not in {
        item.relative for item in plan_task(source, status.task_id, snapshot=status).files
    }
