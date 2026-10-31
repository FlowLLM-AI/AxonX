"""Verify storage publication, incremental reads and immutable input contracts."""

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import polars as pl
import pytest
from clock_helpers import FakeClock

from axonx.task.core.base import BaseTask
from axonx.task.core.clock import DeadlineBudget
from axonx.task.models.artifacts import ArtifactRecord, task_protocol
from axonx.task.models.events import ProgressEvent
from axonx.task.models.identity import TaskState, TaskType
from axonx.task.models.lifecycle import (
    DisplayReplica,
    InputSource,
    ReplicaFile,
    ReplicaLog,
    TaskMetadata,
    TaskStepStatus,
)
from axonx.task.models.params import BaseOutputParams
from axonx.task.runtime.executor import TaskExecutor
from axonx.task.storage.artifacts import artifact_record, verify_artifact
from axonx.task.storage.files import atomic_write_json, copy_file, file_revision
from axonx.task.storage.inputs import (
    read_upstream_metadata,
    upstream_artifact,
    upstream_artifacts,
    upstream_input_artifact,
    upstream_task_directory,
    verify_input_sources,
)
from axonx.task.storage.logs import TaskJournal, TaskLogReader
from axonx.task.storage.online import publish_online
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


def test_upstream_inputs_resolve_the_published_files_directly(tmp_path, record):
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
    (resolved,) = upstream_artifacts(consumer, record.task_id, "dataset")
    assert resolved == source
    assert not consumer.task_dir.exists()
    replacement = directory / "new.bin"
    replacement.write_bytes(b"refreshed output")
    replacement.replace(source)
    with pytest.raises(ValueError, match="Artifact revision mismatch"):
        upstream_artifacts(consumer, record.task_id, "dataset", metadata=metadata)
    # Pinning an earlier record must still reject a newly published display replica.
    record.replica = DisplayReplica(source_revision="source", policy_revision="policy", files={})
    write_task_metadata(directory, record)
    with pytest.raises(ValueError, match="Display replicas"):
        upstream_artifacts(consumer, record.task_id, "dataset", metadata=metadata)


@pytest.mark.parametrize("change", [None, "execution", "publication", "file"])
def test_indirect_inputs_require_the_execution_and_revision_consumed_by_the_parent(tmp_path, record, change):
    directory = task_path(tmp_path, record.task_id)
    path = directory / "data.bin"
    path.write_bytes(b"original")
    original = artifact_record(path, directory)
    record.output_params = {"artifacts": {"dataset": original}}
    write_task_metadata(directory, record)
    parent = {
        "input_sources": {
            record.task_id: {"started_at": record.started_at.isoformat(), "artifacts": {"dataset": original}}
        }
    }
    consumer = SimpleNamespace(
        workspace_path=tmp_path,
        upstream_task_dir=lambda task_id: upstream_task_directory(tmp_path, task_id),
    )
    if change == "execution":
        record.started_at += timedelta(seconds=1)
    elif change in ("publication", "file"):
        path.write_bytes(b"replacement")
        if change == "publication":
            record.output_params["artifacts"]["dataset"] = artifact_record(path, directory)
    write_task_metadata(directory, record)
    if change is None:
        assert upstream_input_artifact(consumer, parent, record.task_id, "dataset") == path
    else:
        with pytest.raises(ValueError, match="execution changed|input changed|revision mismatch"):
            upstream_input_artifact(consumer, parent, record.task_id, "dataset")


@pytest.mark.parametrize("change", ["unchanged", "file", "execution"])
def test_direct_inputs_record_provenance_and_reject_changes(tmp_path, record, change):
    directory = task_path(tmp_path, record.task_id)
    source = directory / "data.bin"
    source.write_bytes(b"published")
    record.output_params = {"artifacts": {"dataset": artifact_record(source, directory)}}
    write_task_metadata(directory, record)

    class Consumer(BaseTask):
        def build_task_steps(self):
            yield self.consume

        def consume(self):
            path, _ = upstream_artifact(self, record.task_id, "dataset")
            assert path == source
            assert path.read_bytes() == b"published"
            assert not (self.task_dir / "inputs").exists()
            if change == "file":
                source.write_bytes(b"replaced input")
            elif change == "execution":
                record.started_at += timedelta(seconds=1)
                write_task_metadata(directory, record)

        def build_output_params(self):
            return BaseOutputParams()

    consumer = Consumer({}, workspace_path=tmp_path, reg_name="consumer")
    if change == "unchanged":
        status = TaskExecutor().execute(consumer)
        reference = status.input_sources[record.task_id]
        assert reference.started_at == record.started_at
        assert reference.artifacts["dataset"].revision == file_revision(source)
    else:
        with pytest.raises(ValueError, match="revision mismatch|execution changed"):
            TaskExecutor().execute(consumer)
        assert consumer.metadata.state == TaskState.FAILED


@pytest.mark.parametrize("change", ["unchanged", "revoked", "execution", "file"])
def test_completed_window_inputs_are_valid_while_their_producer_runs(tmp_path, record, change):
    directory = task_path(tmp_path, record.task_id)
    path = directory / "1045_bar_data.parquet"
    pl.DataFrame({"ts_code": ["A"], "close": [10]}).write_parquet(path)
    artifact = artifact_record(path, directory)
    record.state = TaskState.RUNNING
    record.output_params = {"windows": [{"key": "1045_bar", "status": "done", "artifacts": {"data": artifact}}]}
    consumer = SimpleNamespace(
        workspace_path=tmp_path,
        metadata=SimpleNamespace(
            input_sources={
                record.task_id: InputSource(started_at=record.started_at, artifacts={"1045_bar/data": artifact}),
            }
        ),
    )
    if change == "revoked":
        record.output_params["windows"][0]["status"] = "incomplete"
    elif change == "execution":
        record.started_at += timedelta(seconds=1)
    elif change == "file":
        path.write_text("changed")
    write_task_metadata(directory, record)
    if change == "unchanged":
        verify_input_sources(consumer)
    else:
        with pytest.raises(ValueError, match="no longer published|execution changed|revision mismatch"):
            verify_input_sources(consumer)


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


def test_copy_revision_mismatch_preserves_the_previous_target(tmp_path):
    source, target = tmp_path / "source", tmp_path / "target"
    source.write_text("original", encoding="utf-8")
    expected = file_revision(source)
    target.write_text("previous", encoding="utf-8")
    source.write_text("refreshed contents", encoding="utf-8")
    with pytest.raises(ValueError, match="Source revision mismatch"):
        copy_file(source, target, expected_revision=expected)
    assert target.read_text() == "previous"
    assert {path.name for path in tmp_path.iterdir()} == {"source", "target"}


def test_source_changes_during_copy_preserve_the_previous_target(tmp_path, monkeypatch):
    from axonx.task.storage import files

    source, target = tmp_path / "source", tmp_path / "target"
    source.write_bytes(b"original")
    target.write_bytes(b"previous")
    copy = files.shutil.copy2

    def changed(source, destination):
        copy(source, destination)
        source.write_bytes(b"refreshed while copying")

    monkeypatch.setattr(files.shutil, "copy2", changed)
    with pytest.raises(ValueError, match="Source changed during copy"):
        copy_file(source, target)
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


def test_online_publication_uses_regular_outputs_and_respects_deadline(tmp_path):
    source = tmp_path / "signals.parquet"
    frame = pl.DataFrame({"ts_code": ["A"], "pred": [1.0]})
    frame.write_parquet(source)
    task = SimpleNamespace(
        task_id="inference#demo#online",
        task_dir=tmp_path / "task",
        metadata=SimpleNamespace(started_at=datetime.now(UTC)),
    )
    clock = FakeClock(datetime.now(UTC))
    budget = DeadlineBudget(clock, clock.now() + timedelta(seconds=60))
    commit = publish_online(
        task,
        trade_date="20261026",
        trade_time="0930",
        model_identity={"model": "test"},
        protocol=task_protocol(TaskType.INFERENCE),
        files={"signals": source},
        budget=budget,
    )
    assert pl.read_parquet(verify_artifact(task.task_dir, commit.artifacts["signals"])).equals(frame)
    assert commit.artifacts["signals"].path == "outputs/0930/signals.parquet"
    assert not (task.task_dir / "persistent").exists()
    clock.sleep(61)
    with pytest.raises(TimeoutError, match="Window deadline exceeded"):
        publish_online(
            task,
            trade_date="20261027",
            trade_time="1000",
            model_identity={"model": "test"},
            protocol=task_protocol(TaskType.INFERENCE),
            files={"signals": source},
            budget=budget,
        )
    assert not (task.task_dir / "outputs/1000").exists()
