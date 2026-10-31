"""Verify application-owned display replica application."""

import gzip
import hashlib
import io
import os
import tarfile
from datetime import timedelta

import polars as pl
import pytest

from axonx.app.components.sync import applier as applier_module
from axonx.app.components.sync import replica as replica_module
from axonx.app.components.sync.applier import FileSyncStore
from axonx.app.components.sync.archive import archive_budget, build_archive, pack_batches
from axonx.app.components.sync.artifacts import plan_task
from axonx.app.components.sync.local import LocalSyncComponent
from axonx.app.components.sync.models import (
    FileGroup,
    FileManifest,
    FileRecord,
    SnapshotChangedError,
    TaskPlan,
)
from axonx.app.components.sync.replica import ReplicaBuilder, prepare_group
from axonx.task.builtins.demo import DemoTask
from axonx.task.models.identity import TaskState
from axonx.task.runtime.executor import TaskExecutor
from axonx.task.storage.logs import TaskLogReader
from axonx.task.storage.workspace import read_entry, task_directory, task_path, write_task_metadata
from axonx.utils.logging import LoggingConfig, configure_logging


def file_group(plans, version, revision):
    return FileGroup.capture(plans, version, revision), plans


def archive_plan(task_id, plan, archive):
    group = file_group({task_directory(task_id): plan}, "publication", max(item.modified_ns for item in plan.files))
    build_archive({"group": group}, archive, source="source")


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
    FileSyncStore(target, budget).apply(archive)
    replica = read_entry(target, status.task_id)
    chunk = TaskLogReader(target).read_status(replica, 0)
    assert chunk.content == content
    assert chunk.next_offset == len(content.encode())
    assert replica.log_path == ""
    assert not (task_path(target, status.task_id) / "task.log").exists()


@pytest.mark.parametrize("budget", [0, -1, True, None])
def test_task_archive_budget_is_validated_before_mutation(tmp_path, budget):
    with pytest.raises(ValueError, match="positive integer"):
        FileSyncStore(tmp_path, budget)


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
    FileSyncStore(target, budget).apply(archive)
    replica = read_entry(target, status.task_id).replica
    assert replica.files[artifact.name].sampled
    assert replica.files[artifact.name].dates == retained


def test_live_metadata_delta_transfers_only_changed_files(tmp_path, source_task):
    source, status, directory = source_task
    status.state, status.finished_at = TaskState.RUNNING, None
    write_task_metadata(directory, status)
    budget = 1_000_000
    logs = TaskLogReader(source)
    prepared = prepare_group(source, status.task_id, tmp_path / "first", budget, logs, {})
    store = FileSyncStore(tmp_path / "target", budget)
    archive = tmp_path / "live.tar.gz"
    build_archive({"group": prepared}, archive, source="source")
    store.apply(archive)
    previous = read_entry(store.root, status.task_id).replica.snapshot
    remote = store.index("source")
    status.output_params["progress"] = 1
    write_task_metadata(directory, status)
    prepared = prepare_group(source, status.task_id, tmp_path / "second", budget, logs, remote["group"])
    build_archive({"group": prepared}, archive, source="source", remote=remote)
    with tarfile.open(archive) as stream:
        assert not any(member.name.endswith("/result.txt") for member in stream.getmembers())
    store.apply(archive)
    assert read_entry(store.root, status.task_id).replica.snapshot.revision > previous.revision
    assert (task_path(store.root, status.task_id) / "result.txt").read_text() == "retained publication"


def test_batches_keep_overlapping_groups_separate_and_reserve_full_size(tmp_path, source_task):
    source, status, _ = source_task
    plan = ReplicaBuilder(source, status.task_id, tmp_path / "prepared", 1_000_000).prepare()
    groups = {
        "first": file_group({"parent": plan, "shared": plan}, "first", 1),
        "second": file_group({"other": plan, "shared": plan}, "second", 1),
        "third": file_group({"independent": plan}, "third", 1),
        "too_large": (
            FileGroup(
                version="large",
                revision=1,
                directories={"large": {"data": FileRecord(size=plan.size * 30, revision="1")}},
            ),
            {},
        ),
    }
    limit = max(groups[name][0].size for name in ("first", "second", "third"))
    batches, oversized, deferred = pack_batches(groups, limit * 5, 1)
    assert batches == [["first"]]
    assert oversized == ["too_large"]
    assert deferred == ["second", "third"]
    batches, _, deferred = pack_batches(groups, limit, 3)
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
    receiver = FileSyncStore(target, budget)
    archive = tmp_path / "replica.tar.gz"
    first = ReplicaBuilder(source, status.task_id, tmp_path / "first", budget).prepare()
    archive_plan(status.task_id, first, archive)
    receiver.apply(archive)
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

    monkeypatch.setattr(applier_module.os, "replace", fail_install)
    with pytest.raises(OSError, match="commit failed"):
        receiver.apply(archive)
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
        prepare_group(source, status.task_id, tmp_path / "prepared", 1_000_000, TaskLogReader(source), {})
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


def file_batch(tmp_path, directories, revision, *, source="source", remote=None, name="view"):
    """Prepare arbitrary bytes; these tests deliberately do not create valid Task metadata."""
    plans = {}
    for relative, files in directories.items():
        directory = tmp_path / f"export-{source}-{revision}" / relative
        directory.mkdir(parents=True, exist_ok=True)
        for filename, content in files.items():
            target = directory / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        plans[relative] = TaskPlan.capture(directory, files)
    prepared = file_group(plans, f"version-{revision}", revision)
    archive = tmp_path / f"batch-{source}-{revision}.tar.gz"
    build_archive({name: prepared}, archive, source=source, remote=remote)
    return archive, prepared[0]


def test_receiver_stores_unknown_metadata_and_recovers_missing_files(tmp_path):
    directory = "tasks/base/future-task"
    contents = {"metadata.json": b'{"unknown_task_format": 42}', "report.bin": b"opaque result"}
    archive, _ = file_batch(tmp_path, {directory: contents}, 1)
    store = FileSyncStore(tmp_path / "receiver", 1_000_000)
    store.apply(archive)
    assert (store.root / directory / "metadata.json").read_bytes() == contents["metadata.json"]
    assert store.index("source")["view"]["version"] == "version-1"
    (store.root / directory / "report.bin").unlink()
    assert not store.index("source")
    store.apply(archive)  # Identical publication is safe to replay after a lost acknowledgement.
    assert (store.root / directory / "report.bin").read_bytes() == contents["report.bin"]
    assert store.index("source")


@pytest.mark.parametrize("other_source", [False, True])
def test_receiver_preserves_unowned_directories(tmp_path, other_source):
    directory = "tasks/base/original"
    store = FileSyncStore(tmp_path / "receiver", 1_000_000)
    original = store.root / directory / "metadata.json"
    if other_source:
        archive, _ = file_batch(tmp_path, {directory: {"metadata.json": b"other source"}}, 1, source="other")
        store.apply(archive)
    else:
        original.parent.mkdir(parents=True)
        original.write_bytes(b"local task")
    before = original.read_bytes()
    archive, _ = file_batch(tmp_path, {directory: {"metadata.json": b"replacement"}}, 2)
    with pytest.raises(ValueError, match="unowned"):
        store.apply(archive)
    assert original.read_bytes() == before
    assert not store.index("source")


def test_receiver_rejects_stale_and_conflicting_publications(tmp_path):
    directory = "tasks/base/ordered"
    store = FileSyncStore(tmp_path / "receiver", 1_000_000)
    archive, _ = file_batch(tmp_path, {directory: {"metadata.json": b"new"}}, 2)
    store.apply(archive)
    for revision in (1, 2):
        archive, _ = file_batch(tmp_path, {directory: {"metadata.json": b"old"}}, revision)
        with pytest.raises(ValueError, match="Stale or conflicting"):
            store.apply(archive)
    assert (store.root / directory / "metadata.json").read_bytes() == b"new"


def test_receipt_and_file_commit_roll_back_together(tmp_path, monkeypatch):
    directory = "tasks/base/transaction"
    store = FileSyncStore(tmp_path / "receiver", 1_000_000)
    archive, _ = file_batch(tmp_path, {directory: {"metadata.json": b"first"}}, 1)
    store.apply(archive)
    previous = store.index("source")
    archive, _ = file_batch(tmp_path, {directory: {"metadata.json": b"second"}}, 2)
    replace = os.replace

    def fail_receipt(incoming, target):
        if incoming.name == "receipt.json":
            raise OSError("receipt commit failed")
        return replace(incoming, target)

    monkeypatch.setattr(applier_module.os, "replace", fail_receipt)
    with pytest.raises(OSError, match="receipt commit failed"):
        store.apply(archive)
    assert (store.root / directory / "metadata.json").read_bytes() == b"first"
    assert store.index("source") == previous


def test_missing_delta_base_requires_resend_without_changing_receipt(tmp_path):
    directory = "tasks/base/delta"
    store = FileSyncStore(tmp_path / "receiver", 1_000_000)
    contents = {"metadata.json": b"first", "result.bin": b"unchanged"}
    archive, prepared = file_batch(tmp_path, {directory: contents}, 1)
    store.apply(archive)
    previous = store.index("source")
    # Reuse an actual unchanged exported file revision in the next publication.
    files = dict(prepared.directories[directory])
    files["metadata.json"] = type(files["metadata.json"])(size=6, revision="second")
    group = FileGroup(version="second", revision=2, directories={directory: files})
    archive = tmp_path / "delta.tar.gz"
    manifest = FileManifest(source="source", groups={"view": group})
    with tarfile.open(archive, "w:gz") as stream:
        for name, content in (
            ("sync-manifest.json", manifest.model_dump_json().encode()),
            (directory + "/metadata.json", b"second"),
        ):
            member = tarfile.TarInfo(name)
            member.size = len(content)
            stream.addfile(member, io.BytesIO(content))
    result = store.root / directory / "result.bin"
    result.unlink()
    with pytest.raises((OSError, ValueError)):
        store.apply(archive)
    assert (store.root / directory / "metadata.json").read_bytes() == b"first"
    result.write_bytes(contents["result.bin"])
    assert store.index("source") == previous
    store.apply(archive)
    assert (store.root / directory / "metadata.json").read_bytes() == b"second"


def test_group_removal_keeps_directories_owned_by_another_group(tmp_path):
    shared, exclusive = "tasks/base/shared", "tasks/base/exclusive"
    store = FileSyncStore(tmp_path / "receiver", 1_000_000)
    archive, _ = file_batch(tmp_path, {shared: {"data": b"shared"}, exclusive: {"data": b"exclusive"}}, 1)
    store.apply(archive)
    archive, _ = file_batch(tmp_path, {shared: {"data": b"shared"}}, 2, name="other")
    store.apply(archive)
    archive, _ = file_batch(tmp_path, {}, 3)
    report = store.apply(archive)
    assert report.deleted == [exclusive]
    assert (store.root / shared / "data").read_bytes() == b"shared"
    assert not (store.root / exclusive).exists()


@pytest.mark.parametrize("kind", ["oversized", "symlink", "undeclared", "noncanonical", "duplicate", "traversal"])
def test_invalid_file_manifests_and_payloads_leave_receipts_unchanged(tmp_path, kind):
    directory = "tasks/base/validated"
    store = FileSyncStore(tmp_path / "receiver", 100_000)
    archive, prepared = file_batch(tmp_path, {directory: {"metadata.json": b"old"}}, 1)
    store.apply(archive)
    previous = store.index("source")
    manifest = FileManifest(source="source", groups={"view": prepared.model_copy(deep=True)})
    manifest.groups["view"].revision = 2
    if kind == "oversized":
        manifest.groups["view"].directories[directory]["metadata.json"].size = 200_000
    if kind == "noncanonical":
        manifest.groups["view"].directories[directory + "/../escape"] = manifest.groups["view"].directories.pop(
            directory
        )
    invalid = tmp_path / "invalid-manifest.tar.gz"
    with tarfile.open(invalid, "w:gz") as stream:
        content = manifest.model_dump_json().encode()
        member = tarfile.TarInfo("sync-manifest.json")
        member.size = len(content)
        stream.addfile(member, io.BytesIO(content))
        if kind in {"symlink", "undeclared", "duplicate", "traversal"}:
            name = directory + "/metadata.json" if kind in {"symlink", "duplicate"} else directory + "/unexpected"
            member = tarfile.TarInfo("../outside" if kind == "traversal" else name)
            if kind == "symlink":
                member.type, member.linkname = tarfile.SYMTYPE, "/outside"
                stream.addfile(member)
            else:
                member.size = 3
                stream.addfile(member, io.BytesIO(b"new"))
                if kind == "duplicate":
                    stream.addfile(member, io.BytesIO(b"new"))
    with pytest.raises(ValueError):
        store.apply(invalid)
    assert (store.root / directory / "metadata.json").read_bytes() == b"old"
    assert store.index("source") == previous


def test_delayed_group_cannot_regress_a_shared_directory(tmp_path):
    directory = "tasks/base/shared"
    store = FileSyncStore(tmp_path / "receiver", 1_000_000)
    first, _ = file_batch(tmp_path, {directory: {"metadata.json": b"first"}}, 1)
    store.apply(first)
    delayed, _ = file_batch(tmp_path, {directory: {"metadata.json": b"delayed"}}, 2)
    newest, _ = file_batch(tmp_path, {directory: {"metadata.json": b"newest"}}, 3, name="other")
    store.apply(newest)
    with pytest.raises(ValueError, match="Stale or conflicting shared"):
        store.apply(delayed)
    assert (store.root / directory / "metadata.json").read_bytes() == b"newest"


def test_old_receipt_cannot_overwrite_a_locally_recreated_directory(tmp_path):
    directory = "tasks/base/recreated"
    store = FileSyncStore(tmp_path / "receiver", 1_000_000)
    archive, _ = file_batch(tmp_path, {directory: {"metadata.json": b"replica"}}, 1)
    store.apply(archive)
    target = store.root / directory
    target.rename(tmp_path / "old-replica")
    target.mkdir()
    (target / "metadata.json").write_bytes(b"new local task")
    assert not store.index("source")
    archive, _ = file_batch(tmp_path, {directory: {"metadata.json": b"updated replica"}}, 2)
    with pytest.raises(ValueError, match="unowned"):
        store.apply(archive)
    assert (target / "metadata.json").read_bytes() == b"new local task"
    tombstone, _ = file_batch(tmp_path, {}, 3)
    with pytest.raises(ValueError, match="unowned"):
        store.apply(tombstone)
    assert target.is_dir()


def test_oversized_archive_header_is_rejected_before_its_payload_is_read(tmp_path):
    archive = tmp_path / "oversized-header.tar.gz"
    member = tarfile.TarInfo("sync-manifest.json")
    member.size = 10_000_000
    with gzip.open(archive, "wb") as stream:
        stream.write(member.tobuf())
    with pytest.raises(ValueError, match="expands beyond"):
        FileSyncStore(tmp_path / "receiver", 100_000).apply(archive)
