"""Verify storage publication, incremental reads and immutable input contracts."""

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from axonx.task.core.clock import DeadlineBudget, WindowClock
from axonx.task.models.artifacts import ArtifactRecord, task_protocol
from axonx.task.models.events import ProgressEvent
from axonx.task.models.identity import TaskState, TaskType
from axonx.task.models.lifecycle import DisplayReplica, ReplicaFile, ReplicaLog, TaskMetadata, TaskStepStatus
from axonx.task.models.reports import HISTORY_BLOCK_SIZE
from axonx.task.runtime.replay import ReplayClock
from axonx.task.storage.artifacts import artifact_record, verify_artifact
from axonx.task.storage.files import atomic_write_json, file_revision, snapshot_file
from axonx.task.storage.inputs import (
    pin_upstream_artifacts,
    read_upstream_metadata,
    snapshot_model_collection,
    upstream_artifact,
    upstream_task_directory,
)
from axonx.task.storage.logs import TaskJournal, TaskLogReader
from axonx.task.storage.online import OnlineStore, pin_online_history, read_online_history
from axonx.task.storage.workspace import load_task_metadata, scan_entries, scan_metadata, task_path, write_task_metadata


@pytest.fixture
def record(tmp_path):
    now = datetime.now(UTC)
    metadata = TaskMetadata(
        version=1,
        task_id="base#demo#stored",
        task_type=TaskType.BASE,
        reg_name="demo",
        state=TaskState.SUCCEEDED,
        pid=os.getpid(),
        machine_id="test",
        process_started_at=now,
        started_at=now,
    )
    write_task_metadata(task_path(tmp_path, metadata.task_id), metadata)
    return metadata


def test_source_metadata_and_input_snapshots_share_the_published_record(tmp_path, record):
    directory = task_path(tmp_path, record.task_id)
    source = directory / "data.bin"
    source.write_bytes(b"published")
    record.output_params = {"artifacts": {"dataset": artifact_record(source, directory)}}
    write_task_metadata(directory, record)
    root, metadata = read_upstream_metadata(tmp_path, record.task_id)
    assert root == directory
    assert metadata == record.model_dump(mode="json")
    consumer = SimpleNamespace(
        workspace_path=tmp_path,
        task_dir=tmp_path / "consumer",
        upstream_task_dir=lambda task_id: upstream_task_directory(tmp_path, task_id),
    )
    assert upstream_artifact(consumer, record.task_id, "dataset") == (source, metadata)
    (pinned,) = pin_upstream_artifacts(consumer, record.task_id, "dataset")
    replacement = directory / "new.bin"
    replacement.write_bytes(b"refreshed output")
    replacement.replace(source)
    with pytest.raises(ValueError, match="Artifact revision mismatch"):
        pin_upstream_artifacts(consumer, record.task_id, "dataset", metadata=metadata)
    assert pinned.read_bytes() == b"published"
    # Pinning an earlier record must still reject a newly published display replica.
    record.replica = DisplayReplica(source_revision="source", policy_revision="policy", files={})
    write_task_metadata(directory, record)
    with pytest.raises(ValueError, match="Display replicas"):
        pin_upstream_artifacts(consumer, record.task_id, "dataset", metadata=metadata)


def test_current_metadata_roundtrips_without_rewriting_relationships(tmp_path, record):
    directory = task_path(tmp_path, record.task_id)
    payload = record.model_dump(mode="json")
    payload.update(
        report_kind="online_pipeline",
        input_params={"upstream_task_ids": ["etl#data#daily"]},
        output_params={"protocol": {"market_upstream_task_id": "etl#data#daily"}},
        children=[
            {
                "node_name": "child",
                "attempt": 1,
                "reg_name": "demo",
                "child_task_id": "base#demo#child",
                "state": "failed",
                "exit_code": 1,
            }
        ],
    )
    path = directory / "metadata.json"
    atomic_write_json(path, payload)
    original = path.read_bytes()
    metadata = load_task_metadata(directory, record.task_id)
    assert metadata.children[0].child_task_id == "base#demo#child"
    assert metadata.children[0].reg_name == "demo"
    assert metadata.input_params == payload["input_params"]
    assert metadata.output_params == payload["output_params"]
    assert path.read_bytes() == original
    write_task_metadata(directory, metadata)
    assert load_task_metadata(directory, record.task_id) == metadata


@pytest.mark.parametrize(
    "changes",
    [
        {"source": {"kind": "exec"}},
        {"category": "online_prediction"},
        {"state": "cancelled"},
        {"children": [{"node_name": "old", "attempt": 1, "task": "demo", "task_id": "base#demo#old"}]},
    ],
)
def test_retired_metadata_fields_are_rejected_without_mutating_files(tmp_path, record, changes):
    directory = task_path(tmp_path, record.task_id)
    path = directory / "metadata.json"
    atomic_write_json(path, {**record.model_dump(mode="json"), **changes})
    original = path.read_bytes()
    with pytest.raises(ValueError, match="Invalid Task metadata"):
        load_task_metadata(directory, record.task_id)
    assert path.read_bytes() == original


@pytest.mark.parametrize("problem", ["running", "failed", "replica", "identity"])
def test_upstream_metadata_rejects_unusable_publications(tmp_path, record, problem):
    directory = task_path(tmp_path, record.task_id)
    task_id = record.task_id
    if problem == "replica":
        record.replica = DisplayReplica(source_revision="source", policy_revision="policy", files={})
    elif problem == "identity":
        record.task_id = "base#demo#other"
    else:
        record.state = TaskState(problem)
    write_task_metadata(directory, record)
    with pytest.raises(ValueError):
        read_upstream_metadata(tmp_path, task_id)


def test_incremental_scan_retries_corrupt_records_and_removes_missing_records(tmp_path, record):
    entries, versions = scan_metadata(tmp_path, {}, {})
    path = task_path(tmp_path, record.task_id) / "metadata.json"
    path.write_text("{incomplete", encoding="utf-8")
    assert scan_entries(tmp_path) == {}
    retained, old_versions = scan_metadata(tmp_path, entries, versions)
    assert retained[record.task_id] is entries[record.task_id]
    assert old_versions == versions

    record.output_params = {"result": 42}
    write_task_metadata(path.parent, record)
    updated, new_versions = scan_metadata(tmp_path, retained, old_versions)
    assert updated[record.task_id].output_params == {"result": 42}
    assert new_versions != versions
    path.unlink()
    assert scan_metadata(tmp_path, updated, new_versions) == ({}, {})


def test_scans_ignore_symlinks_invalid_ids_and_nested_artifact_directories(tmp_path, record):
    directory = task_path(tmp_path, record.task_id)
    write_task_metadata(directory / "base#demo#nested", record)
    write_task_metadata(tmp_path / "base" / "invalid", record)
    (tmp_path / "base" / "base#demo#linked").symlink_to(directory, target_is_directory=True)
    (tmp_path / "train").symlink_to(directory.parent, target_is_directory=True)
    assert set(scan_entries(tmp_path)) == {record.task_id}
    assert set(scan_metadata(tmp_path, {}, {})[0]) == {record.task_id}


def test_incremental_scan_propagates_io_errors_without_mutating_its_cache(tmp_path, record, monkeypatch):
    entries, versions = scan_metadata(tmp_path, {}, {})
    path = task_path(tmp_path, record.task_id) / "metadata.json"
    path.write_text("changed", encoding="utf-8")

    def denied(*args, **kwargs):
        raise PermissionError("unreadable metadata")

    monkeypatch.setattr(Path, "read_text", denied)
    with pytest.raises(PermissionError, match="unreadable metadata"):
        scan_metadata(tmp_path, entries, versions)
    assert entries[record.task_id] == record
    assert versions


def test_journal_keeps_partial_utf8_lines_and_restarts_after_truncation(tmp_path):
    journal = TaskJournal(tmp_path / "events.jsonl")
    assert journal.read(0) == (0, [])
    journal.append_snapshots([TaskStepStatus(name="训练", state="done")])
    offset, lines = journal.read(0)
    assert ProgressEvent.model_validate_json(lines[0]).name == "训练"
    pending = ProgressEvent(name="结束").model_dump_json().encode("utf-8")
    with journal.path.open("ab") as handle:
        handle.write(pending[:-1])
    assert journal.read(offset) == (offset, [])
    with journal.path.open("ab") as handle:
        handle.write(pending[-1:] + b"\n")
    end, lines = journal.read(offset)
    assert ProgressEvent.model_validate_json(lines[0]).name == "结束"
    journal.path.write_bytes(b"{}\n")
    assert journal.read(end) == (3, ["{}"])


def test_log_chunks_keep_utf8_boundaries_and_reset_after_truncation(tmp_path):
    path = tmp_path / "task.log"
    path.write_text("开始🙂end", encoding="utf-8")
    reader = TaskLogReader(tmp_path)
    offset = 0
    content = []
    while offset < path.stat().st_size:
        chunk = reader.read(path, offset, limit=2)
        assert chunk.next_offset > offset
        assert "\ufffd" not in chunk.content
        offset = chunk.next_offset
        content.append(chunk.content)
    assert "".join(content) == "开始🙂end"
    path.write_text("新", encoding="utf-8")
    chunk = reader.read(path, offset, limit=2)
    assert chunk.reset and chunk.content == "新"


def test_snapshot_revision_mismatch_preserves_the_previous_target(tmp_path):
    source, target = tmp_path / "source", tmp_path / "target"
    source.write_text("original", encoding="utf-8")
    expected = file_revision(source)
    target.write_text("previous", encoding="utf-8")
    source.write_text("refreshed contents", encoding="utf-8")
    with pytest.raises(ValueError, match="Source revision mismatch"):
        snapshot_file(source, target, expected_revision=expected)
    assert target.read_text() == "previous"
    assert {path.name for path in tmp_path.iterdir()} == {"source", "target"}


def test_source_changes_during_snapshot_preserve_the_previous_target(tmp_path, monkeypatch):
    from axonx.task.storage import files

    source, target = tmp_path / "source", tmp_path / "target"
    source.write_bytes(b"original")
    target.write_bytes(b"previous")
    copy = files.shutil.copy2

    def changed(source, destination):
        copy(source, destination)
        source.write_bytes(b"refreshed while copying")

    monkeypatch.setattr(files.shutil, "copy2", changed)
    with pytest.raises(ValueError, match="Source changed during snapshot"):
        snapshot_file(source, target, isolated=True)
    assert target.read_bytes() == b"previous"
    assert {path.name for path in tmp_path.iterdir()} == {"source", "target"}


def test_log_reader_rejects_paths_linked_outside_the_log_directory(tmp_path):
    directory = tmp_path / "logs"
    directory.mkdir()
    external = tmp_path / "external.log"
    external.write_text("external content", encoding="utf-8")
    linked = directory / "linked.log"
    linked.symlink_to(external)
    with pytest.raises(ValueError, match="outside the configured log directory"):
        TaskLogReader(directory).read(linked)


@pytest.mark.parametrize("relative", ["tasks", "tasks/base", "tasks/base/base#demo#stored"])
@pytest.mark.parametrize("replica", [False, True])
def test_task_log_reader_rejects_symlinked_task_ancestors(tmp_path, record, relative, replica):
    directory = task_path(tmp_path, record.task_id)
    (directory / "task.log").write_text("private")
    record.log_path = "task.log"
    if replica:
        record.replica = DisplayReplica(
            source_revision="source",
            policy_revision="policy",
            files={"task.log": ReplicaFile(size=7, revision="1")},
            log=ReplicaLog(path="task.log", start=0, end=7),
        )
    linked = tmp_path / relative
    destination = tmp_path / "moved"
    linked.rename(destination)
    linked.symlink_to(destination, target_is_directory=True)
    with pytest.raises(ValueError, match="symlinks"):
        TaskLogReader(tmp_path).read_status(record)


def test_artifact_verification_rejects_symlinks_and_inconsistent_sizes(tmp_path):
    payload = tmp_path / "payload"
    payload.write_bytes(b"data")
    record = ArtifactRecord(**artifact_record(payload, tmp_path))
    assert verify_artifact(tmp_path, record) == payload
    with pytest.raises(ValueError, match="Artifact revision mismatch"):
        verify_artifact(tmp_path, record.model_copy(update={"size": 99}))
    link = tmp_path / "link"
    link.symlink_to(payload)
    with pytest.raises(ValueError, match="symlinks"):
        verify_artifact(tmp_path, record.model_copy(update={"path": "link"}))


def test_model_snapshot_copies_shared_payload_once_and_rejects_stale_files(tmp_path):
    source = tmp_path / "model.bin"
    source.write_bytes(b"model")
    manifest = tmp_path / "source.json"
    value = task_protocol(
        TaskType.TRAIN,
        feature_protocol=task_protocol(TaskType.ETL),
        members={key: {"model_artifact": "weights", "model": {}} for key in ("first", "second")},
        artifacts={"weights": artifact_record(source, tmp_path)},
    )
    atomic_write_json(manifest, value)
    root = tmp_path / "snapshot"
    snapshot = snapshot_model_collection(manifest, root, expected_revision=file_revision(manifest))
    saved = json.loads(snapshot.read_text())
    assert len(list((root / "members").rglob("*.bin"))) == 1
    pinned = verify_artifact(root, ArtifactRecord(**saved["artifacts"]["weights"]))
    assert pinned.read_bytes() == b"model"
    # Atomic source replacement leaves the immutable input snapshot intact.
    replacement = tmp_path / "new.bin"
    replacement.write_bytes(b"new model")
    replacement.replace(source)
    assert pinned.read_bytes() == b"model"
    with pytest.raises(ValueError, match="Artifact revision mismatch"):
        snapshot_model_collection(manifest, tmp_path / "stale")
    assert not (tmp_path / "stale" / "models.json").exists()


def test_online_history_spans_frozen_blocks_and_pins_isolated_inputs(tmp_path):
    source = tmp_path / "signals.csv"
    source.write_text("signals", encoding="utf-8")
    directory = tmp_path / "inference" / "inference#demo#online"
    task = SimpleNamespace(
        task_id=directory.name,
        task_dir=directory,
        persistent_dir=directory / "persistent",
        metadata=SimpleNamespace(started_at=datetime.now(UTC)),
    )
    budget = DeadlineBudget(WindowClock(), datetime.now(UTC) + timedelta(minutes=1))
    store = OnlineStore(task)
    strategy = "a" * 64
    history = store.history(strategy)
    snapshots = []
    for _ in range(HISTORY_BLOCK_SIZE + 1):
        commit, snapshot = store.commit(
            history=history,
            trade_date="20261026",
            trade_time="0930",
            model_identity={"model": "test"},
            protocol=task_protocol(TaskType.INFERENCE),
            files={"signals": source},
            budget=budget,
        )
        history = store.history(strategy)
        assert read_online_history(snapshot) == history
        snapshots.append(snapshot)
    assert commit.revision == HISTORY_BLOCK_SIZE + 1
    assert json.loads(snapshots[-1].read_text())["previous"]

    consumer = SimpleNamespace(task_dir=tmp_path / "consumer", upstream_task_dir=lambda _: directory)
    pinned, manifest = pin_online_history(consumer, task.task_id)
    assert read_online_history(manifest) == pinned
    payload = verify_artifact(consumer.task_dir, pinned.commits[0].artifacts["signals"])
    original = verify_artifact(directory, history.commits[0].artifacts["signals"])
    original.write_text("changed upstream", encoding="utf-8")
    assert payload.read_text() == "signals"

    before = store.manifest.read_bytes()
    folders = set((store.root / "commits").iterdir())

    def fail_prepare(*_):
        raise RuntimeError("report failed")

    with pytest.raises(RuntimeError, match="report failed"):
        store.commit(
            history=history,
            trade_date="20261026",
            trade_time="0930",
            model_identity={"model": "test"},
            protocol=task_protocol(TaskType.INFERENCE),
            files={"signals": source},
            budget=budget,
            prepare=fail_prepare,
        )
    assert store.manifest.read_bytes() == before
    assert set((store.root / "commits").iterdir()) == folders

    clock = ReplayClock(datetime.now(UTC))
    expired_budget = DeadlineBudget(clock, clock.now() + timedelta(seconds=60))

    def expire(*_):
        clock.sleep(61)

    with pytest.raises(TimeoutError, match="Window deadline exceeded"):
        store.commit(
            history=history,
            trade_date="20261026",
            trade_time="0930",
            model_identity={"model": "test"},
            protocol=task_protocol(TaskType.INFERENCE),
            files={"signals": source},
            budget=expired_budget,
            prepare=expire,
        )
    assert store.manifest.read_bytes() == before
    assert set((store.root / "commits").iterdir()) == folders

    # Portable histories may use a full history as the base of a frozen chain.
    boundary = snapshots[HISTORY_BLOCK_SIZE - 1]
    atomic_write_json(boundary, read_online_history(boundary).model_dump(mode="json"))
    node = json.loads(snapshots[-1].read_text())
    node["previous"] = artifact_record(boundary, directory)
    atomic_write_json(snapshots[-1], node)
    assert read_online_history(snapshots[-1]) == history

    snapshots[HISTORY_BLOCK_SIZE - 1].write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="Artifact revision mismatch"):
        read_online_history(snapshots[-1])
