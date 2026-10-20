"""Display replicas preserve source semantics, whole days and atomic application."""

import json
import os
from pathlib import Path

import polars as pl
import pytest

from axonx.task.storage.artifacts import artifact_record, read_metadata
from axonx.task.storage.logs import TaskLogReader
from axonx.task.storage.workspace import (
    TaskMetadata,
    read_entry,
    task_path,
    write_task_metadata,
)
from axonx.task.sync import (
    SnapshotChangedError,
    TaskArchiveApplier,
    build_archive,
    plan_task,
)
from axonx.task.sync.index import (
    policy_revision,
    source_revision,
    snapshot_index,
    verify_replica,
)
from axonx.task.sync.planner import archive_budget
from axonx.task.sync.replica import prepare_replica

TASK_ID = "etl#demo#research-core"


def source_task(root: Path, task_id=TASK_ID):
    directory = task_path(root, task_id)
    directory.mkdir(parents=True)
    metadata = TaskMetadata(
        version=1,
        task_id=task_id,
        run_id="source-run",
        task_type=task_id.split("#")[0],
        state="succeeded",
        log_path="/source/logs/run.log",
    )
    write_task_metadata(directory, metadata)
    return directory, metadata


def publish(directory, metadata, **files):
    metadata.output_params = {"artifacts": {name: artifact_record(path, directory) for name, path in files.items()}}
    write_task_metadata(directory, metadata)


def dataset(path, days=6, rows=256):
    dates = [f"202601{day + 1:02d}" for day in range(days)]
    frame = pl.DataFrame(
        {
            "trade_date": [day for day in dates for _ in range(rows)],
            "value": [os.urandom(256).hex() for _ in range(days * rows)],
        }
    )
    frame.write_parquet(path, compression="zstd")
    return frame


def test_only_published_outputs_and_manifest_dependencies_are_selected(tmp_path):
    directory, metadata = source_task(tmp_path)
    (directory / "inputs").mkdir()
    (directory / "inputs/dataset.parquet").write_bytes(b"large input")
    (directory / "scratch.bin").write_bytes(b"temporary")
    (directory / "model.pt").write_bytes(b"weights")
    manifest = directory / "models.json"
    manifest.write_text(json.dumps({"artifacts": {"weights": artifact_record(directory / "model.pt", directory)}}))
    publish(directory, metadata, models=manifest)
    assert {item.relative for item in plan_task(tmp_path, TASK_ID).files} == {
        "metadata.json",
        "models.json",
        "model.pt",
    }


def test_provenance_and_child_task_paths_are_not_local_dependencies(tmp_path):
    directory, metadata = source_task(tmp_path)
    protocol = directory / "protocol.json"
    protocol.write_text(json.dumps({"realtime_inputs": {"files": {"data": {"path": "data.csv", "sha256": "0" * 64}}}}))
    publish(directory, metadata, protocol=protocol)
    metadata.output_params["models"] = {
        "child": {"comparison": {"artifacts": {"diff": {"path": "../child.csv", "sha256": "0" * 64}}}}
    }
    write_task_metadata(directory, metadata)
    plan = plan_task(tmp_path, TASK_ID)
    assert {item.relative for item in plan.files} == {"metadata.json", "protocol.json"}
    assert not plan.omitted


def test_model_dependencies_keep_file_relative_paths_even_when_missing(tmp_path):
    directory, metadata = source_task(tmp_path)
    folder = directory / "models"
    folder.mkdir()
    weights = folder / "weights.pt"
    weights.write_bytes(b"weights")
    record = artifact_record(weights, folder)
    manifest = folder / "models.json"
    manifest.write_text(json.dumps({"members": {}, "artifacts": {"weights": record}}))
    publish(directory, metadata, models=manifest)
    assert "models/weights.pt" in {item.relative for item in plan_task(tmp_path, TASK_ID).files}
    weights.unlink()
    assert plan_task(tmp_path, TASK_ID).omitted == {"models/weights.pt": "published artifact is missing"}


def test_missing_outputs_sync_status_logs_and_available_files_then_recover(tmp_path):
    source, remote = tmp_path / "source", tmp_path / "remote"
    remote.mkdir()
    directory, metadata = source_task(source)
    present, missing = directory / "present.txt", directory / "missing.txt"
    present.write_text("available")
    missing.write_text("restored")
    manifest = directory / "manifest.json"
    manifest.write_text(json.dumps({"artifacts": {"missing": artifact_record(missing, directory)}}))
    publish(directory, metadata, present=present, manifest=manifest)
    missing.unlink()
    log_dir = source / "logs"
    log_dir.mkdir()
    log = log_dir / "run.log"
    log.write_text("output unavailable\n")
    metadata.log_path = str(log)
    write_task_metadata(directory, metadata)
    before = source_revision(source, TASK_ID)
    apply = TaskArchiveApplier(remote)
    for attempt in range(2):
        staged = tmp_path / str(attempt)
        plan = prepare_replica(
            source,
            TASK_ID,
            task_path(staged, TASK_ID),
            128 * 1024,
            TaskLogReader(log_dir),
        )
        archive = tmp_path / f"{attempt}.tar.gz"
        build_archive({TASK_ID: plan}, [TASK_ID], archive)
        apply.apply(archive, [])
        actual = read_entry(remote, TASK_ID)
        assert actual.state == metadata.state and actual.output_params == metadata.output_params
        assert (task_path(remote, TASK_ID) / "present.txt").read_text() == "available"
        assert TaskLogReader(log_dir).read_status(remote, actual).content == "output unavailable\n"
        verify_replica(remote, TASK_ID)
        if attempt == 0:
            assert actual.replica.omitted == {"missing.txt": "published artifact is missing"}
            missing.write_text("restored")
            assert source_revision(source, TASK_ID) != before
        else:
            assert not actual.replica.omitted
            assert (task_path(remote, TASK_ID) / "missing.txt").read_text() == "restored"


def test_declared_artifact_cannot_escape_task_even_when_missing(tmp_path):
    directory, metadata = source_task(tmp_path)
    metadata.output_params = {"artifacts": {"bad": {"path": "../missing.txt", "sha256": "0" * 64}}}
    write_task_metadata(directory, metadata)
    with pytest.raises(ValueError, match="stay inside"):
        plan_task(tmp_path, TASK_ID)


def test_samples_recent_complete_days_and_keeps_source_unchanged(tmp_path):
    source, staged = tmp_path / "source", tmp_path / "staged"
    directory, metadata = source_task(source)
    original = dataset(directory / "dataset.parquet")
    labels = original.select("trade_date").with_row_index("label")
    labels = pl.concat(
        [
            labels,
            pl.DataFrame(
                {"label": [original.height], "trade_date": ["20271231"]},
                schema=labels.schema,
            ),
        ]
    )
    labels.write_parquet(directory / "labels.parquet")
    calendar = pl.DataFrame({"trade_date": ["20260106", "20271231"]})
    calendar.write_parquet(directory / "calendar.parquet")
    publish(
        directory,
        metadata,
        dataset=directory / "dataset.parquet",
        labels=directory / "labels.parquet",
        calendar=directory / "calendar.parquet",
    )
    identity = source_revision(source, TASK_ID)
    budget = 96 * 1024
    plan = prepare_replica(source, TASK_ID, task_path(staged, TASK_ID), budget)
    replica = read_entry(staged, TASK_ID)
    sample = pl.read_parquet(task_path(staged, TASK_ID) / "dataset.parquet")
    days = sorted(sample["trade_date"].unique().to_list())
    assert 0 < sample.height < original.height
    assert days == sorted(original["trade_date"].unique().to_list())[-len(days) :]
    assert sample.equals(original.filter(pl.col("trade_date").is_in(days)))
    assert set(pl.read_parquet(task_path(staged, TASK_ID) / "labels.parquet")["trade_date"]) == set(days)
    assert plan.size <= archive_budget(budget)
    assert replica.replica.files["dataset.parquet"].source_rows == original.height
    assert replica.replica.files["dataset.parquet"].dates == days
    assert not replica.replica.files["calendar.parquet"].sampled
    assert pl.read_parquet(task_path(staged, TASK_ID) / "calendar.parquet").equals(calendar)
    assert replica.log_path == ""
    assert replica.replica.source_log_path == metadata.log_path
    assert replica.output_params == metadata.output_params
    assert source_revision(source, TASK_ID) == identity
    assert pl.read_parquet(directory / "dataset.parquet").equals(original)
    verify_replica(staged, TASK_ID)
    with pytest.raises(ValueError, match="research inputs"):
        read_metadata(task_path(staged, TASK_ID) / "metadata.json")
    from axonx.task.builtins.stock.backtest import BaseStockBacktestTask

    consumer = BaseStockBacktestTask({}, workspace_path=staged, reg_name="consumer")
    with pytest.raises(ValueError, match="research inputs"):
        consumer.source_task_dir(TASK_ID)
    with pytest.raises(ValueError, match="research inputs"):
        consumer.resolve_workspace_path(task_path(staged, TASK_ID) / "dataset.parquet")


def test_full_outputs_are_not_sampled_when_they_fit(tmp_path):
    directory, metadata = source_task(tmp_path / "source")
    frame = dataset(directory / "predictions.parquet", days=2, rows=4)
    publish(directory, metadata, predictions=directory / "predictions.parquet")
    staged = tmp_path / "staged"
    prepare_replica(tmp_path / "source", TASK_ID, task_path(staged, TASK_ID), 128 * 1024)
    actual = read_entry(staged, TASK_ID)
    assert not actual.replica.files["predictions.parquet"].sampled
    assert pl.read_parquet(task_path(staged, TASK_ID) / "predictions.parquet").equals(frame)


def test_latest_day_too_large_is_omitted_without_partial_rows(tmp_path):
    directory, metadata = source_task(tmp_path / "source")
    dataset(directory / "dataset.parquet", days=1, rows=512)
    publish(directory, metadata, dataset=directory / "dataset.parquet")
    staged = tmp_path / "staged"
    prepare_replica(tmp_path / "source", TASK_ID, task_path(staged, TASK_ID), 32 * 1024)
    actual = read_entry(staged, TASK_ID)
    assert "dataset.parquet" in actual.replica.omitted
    assert not (task_path(staged, TASK_ID) / "dataset.parquet").exists()
    verify_replica(staged, TASK_ID)


@pytest.mark.parametrize("name", ["model.pt", "orders.parquet", "variant_trades.parquet"])
def test_weights_and_full_report_ledgers_are_never_sampled(tmp_path, name):
    directory, metadata = source_task(tmp_path / "source")
    path = directory / name
    if path.suffix == ".parquet":
        dataset(path)
    else:
        path.write_bytes(os.urandom(64 * 1024))
    publish(directory, metadata, output=path)
    original = path.read_bytes()
    prepare_replica(tmp_path / "source", TASK_ID, tmp_path / "staged", 32 * 1024)
    replica = json.loads((tmp_path / "staged/metadata.json").read_text())
    assert replica["replica"]["omitted"][name] == "transfer budget"
    assert not (tmp_path / "staged" / name).exists()
    assert path.read_bytes() == original


def test_replica_roundtrip_and_policy_change(tmp_path):
    directory, metadata = source_task(tmp_path / "source")
    (directory / "report.txt").write_text("full report")
    publish(directory, metadata, report=directory / "report.txt")
    staged, remote = tmp_path / "staged", tmp_path / "remote"
    remote.mkdir()
    budget = 64 * 1024
    plan = prepare_replica(tmp_path / "source", TASK_ID, task_path(staged, TASK_ID), budget)
    archive = tmp_path / "replica.tar.gz"
    build_archive({TASK_ID: plan}, [TASK_ID], archive)
    TaskArchiveApplier(remote, budget).apply(archive, [])
    expected = {
        "source_revision": source_revision(tmp_path / "source", TASK_ID),
        "policy_revision": policy_revision(budget),
    }
    assert all(snapshot_index(remote, frozenset())[TASK_ID][key] == value for key, value in expected.items())
    assert policy_revision(budget + 1) != expected["policy_revision"]
    assert not snapshot_index(tmp_path / "source", frozenset())
    (task_path(remote, TASK_ID) / "report.txt").write_text("tampered")
    assert not snapshot_index(remote, frozenset())


def test_archive_rejects_a_changed_prepared_file(tmp_path):
    directory, metadata = source_task(tmp_path / "source")
    (directory / "report.txt").write_text("before")
    publish(directory, metadata, report=directory / "report.txt")
    plan = prepare_replica(tmp_path / "source", TASK_ID, tmp_path / "staged", 64 * 1024)
    (tmp_path / "staged/report.txt").write_text("after-change")
    with pytest.raises(SnapshotChangedError):
        build_archive({TASK_ID: plan}, [TASK_ID], tmp_path / "archive.tar.gz")


def test_receiver_refuses_unmarked_old_snapshots(tmp_path):
    source_task(tmp_path / "source")
    plan = plan_task(tmp_path / "source", TASK_ID)
    archive = tmp_path / "old.tar.gz"
    build_archive({TASK_ID: plan}, [TASK_ID], archive)
    remote = tmp_path / "remote"
    remote.mkdir()
    with pytest.raises(ValueError, match="display replica"):
        TaskArchiveApplier(remote).apply(archive, [])


def test_receiver_refuses_a_replica_over_its_total_budget(tmp_path):
    directory, metadata = source_task(tmp_path / "source")
    (directory / "report.txt").write_bytes(b"x" * 64 * 1024)
    publish(directory, metadata, report=directory / "report.txt")
    plan = prepare_replica(tmp_path / "source", TASK_ID, tmp_path / "staged", 128 * 1024)
    archive = tmp_path / "oversized.tar.gz"
    build_archive({TASK_ID: plan}, [TASK_ID], archive)
    remote = tmp_path / "remote"
    remote.mkdir()
    with pytest.raises(ValueError, match="expands"):
        TaskArchiveApplier(remote, 32 * 1024).apply(archive, [])


@pytest.mark.parametrize("role", ["targets", "signals"])
def test_display_sync_does_not_validate_research_signal_formats(tmp_path, role):
    directory, metadata = source_task(tmp_path, "backtest#demo#research-core")
    path = directory / f"{role}.parquet"
    path.write_bytes(b"old output")
    publish(directory, metadata, **{role: path})
    assert f"{role}.parquet" in {item.relative for item in plan_task(tmp_path, metadata.task_id).files}


def test_reconciliation_and_replica_index_never_read_payloads(tmp_path, monkeypatch):
    directory, metadata = source_task(tmp_path / "source")
    payload = directory / "report.txt"
    payload.write_text("published payload")
    publish(directory, metadata, report=payload)
    staged = tmp_path / "staged"
    prepare_replica(tmp_path / "source", TASK_ID, task_path(staged, TASK_ID), 64 * 1024)
    original = Path.open

    def metadata_only(path, *args, **kwargs):
        if path.name == "report.txt":
            pytest.fail("Reconciliation read a payload")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", metadata_only)
    assert len(source_revision(tmp_path / "source", TASK_ID)) <= 128
    assert TASK_ID in snapshot_index(staged, frozenset())
