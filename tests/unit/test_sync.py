"""Verify application-owned display replica application."""

import hashlib
import io
import os
import tarfile
from datetime import timedelta

import polars as pl
import pytest

from axonx.app.components.sync import applier as applier_module
from axonx.app.components.sync import replica as replica_module
from axonx.app.components.sync.applier import TaskArchiveApplier, snapshot_index
from axonx.app.components.sync.archive import archive_budget, build_archive, pack_batches
from axonx.app.components.sync.artifacts import plan_task, verify_replica
from axonx.app.components.sync.local import LocalSyncComponent
from axonx.app.components.sync.models import ReplicaBudgetError, SnapshotChangedError
from axonx.app.components.sync.replica import ReplicaBuilder, prepare_group
from axonx.task.builtins.demo import DemoTask
from axonx.task.models.identity import TaskState
from axonx.task.runtime.executor import TaskExecutor
from axonx.task.storage.logs import TaskLogReader
from axonx.task.storage.workspace import METADATA_FILE, read_entry, task_path, write_task_metadata
from axonx.utils.logging import LoggingConfig, configure_logging


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
    build_archive({status.task_id: plan}, archive)
    target = tmp_path / "target"
    TaskArchiveApplier(target, budget).apply(archive, [])
    replica = read_entry(target, status.task_id)
    chunk = TaskLogReader(target).read_status(replica, 0)
    assert chunk.content == content
    assert chunk.next_offset == len(content.encode())
    assert replica.log_path == ""
    assert not (task_path(target, status.task_id) / "task.log").exists()


@pytest.mark.parametrize("budget", [0, -1, True, None])
def test_task_archive_budget_is_validated_before_mutation(tmp_path, budget):
    with pytest.raises(ValueError, match="positive integer"):
        TaskArchiveApplier(tmp_path, budget)


@pytest.mark.parametrize("maximum", [0, -1, True, 1.5])
def test_archive_batch_count_must_be_a_positive_integer(maximum):
    with pytest.raises(ValueError, match="max_archives_per_flush must be a positive integer"):
        LocalSyncComponent(target="example:1024", max_archives_per_flush=maximum)


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf")])
def test_sync_timeout_must_be_finite_and_positive(timeout):
    with pytest.raises(ValueError, match="timeout_seconds must be finite and positive"):
        LocalSyncComponent(target="example:1024", timeout_seconds=timeout)


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
    build_archive({status.task_id: plan}, archive)
    first_archive = archive.read_bytes()
    build_archive({status.task_id: plan}, archive)
    assert archive.read_bytes() == first_archive
    target = tmp_path / "target"
    target.mkdir()
    TaskArchiveApplier(target, budget).apply(archive, [])
    replica = read_entry(target, status.task_id).replica
    assert replica.files[artifact.name].sampled
    assert replica.files[artifact.name].dates == retained


def test_live_metadata_delta_reuses_the_verified_remote_publication(tmp_path, source_task):
    source, status, directory = source_task
    artifact = directory / "result.txt"
    status.state = TaskState.RUNNING
    status.finished_at = None
    write_task_metadata(directory, status)
    budget = 1_000_000
    logs = TaskLogReader(source)
    plans = prepare_group(source, status.task_id, tmp_path / "first", budget, logs, {})
    target = tmp_path / "target"
    target.mkdir()
    applier = TaskArchiveApplier(target, budget)
    archive = tmp_path / "live.tar.gz"
    build_archive(plans, archive)
    applier.apply(archive, [])
    previous = read_entry(target, status.task_id).replica.snapshot

    remote = snapshot_index(target, frozenset(), frozenset({status.task_id}))
    plans = prepare_group(source, status.task_id, tmp_path / "second", budget, logs, remote)
    assert [item.relative for item in plans[status.task_id].files] == [METADATA_FILE]
    build_archive(plans, archive)
    applier.apply(archive, [])
    current = read_entry(target, status.task_id).replica.snapshot
    assert current.revision > previous.revision
    assert (task_path(target, status.task_id) / artifact.name).read_text() == "retained publication"


def test_batches_keep_overlapping_groups_separate_and_reserve_hydrated_size(tmp_path, source_task):
    source, status, _ = source_task
    plan = ReplicaBuilder(source, status.task_id, tmp_path / "prepared", 1_000_000).prepare()
    groups = {
        "first": {"parent": plan, "shared": plan},
        "second": {"other": plan, "shared": plan},
        "third": {"independent": plan},
        "too_large": {"large": type(plan)(plan.files, plan.size * 20)},
    }
    batches, oversized, deferred = pack_batches(groups, plan.size * 10, 1)
    assert batches == [["first"]]
    assert oversized == ["too_large"]
    assert deferred == ["second", "third"]
    batches, _, deferred = pack_batches(groups, plan.size * 2, 3)
    assert batches == [["first"], ["second"], ["third"]]
    assert not deferred


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


@pytest.mark.parametrize("kind", ["duplicate", "symlink", "traversal"])
def test_invalid_archives_leave_the_existing_task_untouched(tmp_path, source_task, kind):
    source, _, directory = source_task
    before = {path.name: path.read_bytes() for path in directory.iterdir() if path.is_file()}
    archive = tmp_path / "invalid.tar.gz"
    name = f"{directory.relative_to(source).as_posix()}/result.txt"
    with tarfile.open(archive, "w:gz") as stream:
        member = tarfile.TarInfo(name if kind != "traversal" else "../outside")
        if kind == "symlink":
            member.type = tarfile.SYMTYPE
            member.linkname = "/outside"
            stream.addfile(member)
        else:
            member.size = 3
            stream.addfile(member, io.BytesIO(b"new"))
            if kind == "duplicate":
                stream.addfile(member, io.BytesIO(b"new"))
    with pytest.raises(ValueError):
        TaskArchiveApplier(source, 1_000_000).apply(archive, [])
    assert {path.name: path.read_bytes() for path in directory.iterdir() if path.is_file()} == before


def test_commit_failure_restores_the_previous_replica(tmp_path, source_task, monkeypatch):
    source, status, directory = source_task
    budget = 1_000_000
    target = tmp_path / "target"
    target.mkdir()
    receiver = TaskArchiveApplier(target, budget)
    archive = tmp_path / "replica.tar.gz"
    first = ReplicaBuilder(source, status.task_id, tmp_path / "first", budget).prepare()
    build_archive({status.task_id: first}, archive)
    receiver.apply(archive, [])
    destination = task_path(target, status.task_id)
    before = {path.name: path.read_bytes() for path in destination.iterdir() if path.is_file()}
    (directory / "result.txt").write_text("new publication")
    second = ReplicaBuilder(source, status.task_id, tmp_path / "second", budget).prepare()
    build_archive({status.task_id: second}, archive)
    replace = os.replace

    def fail_install(incoming, final):
        if "incoming" in incoming.parts and final == destination:
            raise OSError("commit failed")
        return replace(incoming, final)

    monkeypatch.setattr(applier_module.os, "replace", fail_install)
    with pytest.raises(OSError, match="commit failed"):
        receiver.apply(archive, [])
    assert {path.name: path.read_bytes() for path in destination.iterdir() if path.is_file()} == before
    verify_replica(target, status.task_id)


@pytest.mark.parametrize("change", ["restart", "budget"])
def test_metadata_only_refresh_rechecks_source_and_hydrated_budget(tmp_path, source_task, monkeypatch, change):
    source, status, directory = source_task
    status.state = TaskState.RUNNING
    status.finished_at = None
    write_task_metadata(directory, status)
    logs = TaskLogReader(source)
    budget = 1_000_000
    plans = prepare_group(source, status.task_id, tmp_path / "first", budget, logs, {})
    replica_metadata = read_entry(tmp_path / "first", status.task_id)
    remote = {
        "started_at": status.started_at.isoformat(),
        **replica_metadata.replica.model_dump(mode="json"),
    }
    if change == "budget":
        remote["files"]["result.txt"]["size"] = budget
    else:
        write = replica_module.write_task_metadata

        def restart_after_capture(destination, metadata):
            write(destination, metadata)
            status.started_at += timedelta(seconds=1)
            write(directory, status)

        monkeypatch.setattr(replica_module, "write_task_metadata", restart_after_capture)
    assert plans
    with pytest.raises(ReplicaBudgetError if change == "budget" else SnapshotChangedError):
        ReplicaBuilder(
            source,
            status.task_id,
            tmp_path / "refresh",
            archive_budget(budget),
            logs,
            snapshot=replica_metadata.replica.snapshot,
            metadata=status,
            remote=remote,
        ).prepare()
    assert status.replica is None
