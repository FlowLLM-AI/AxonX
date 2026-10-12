"""Display replicas preserve source semantics, whole days and atomic application."""

import os
from pathlib import Path

import polars as pl
import pytest

from axonx.task.storage.artifacts import artifact_record, read_metadata
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
from axonx.task.sync.errors import ReplicaBudgetError
from axonx.task.sync.index import (
    policy_digest,
    snapshot_digest,
    snapshot_index,
    verify_replica,
)
from axonx.task.sync.planner import archive_budget
from axonx.task.sync.replica import prepare_replica

TASK_ID = "etl#demo#axon2-core"


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
    import json

    manifest = directory / "models.json"
    manifest.write_text(json.dumps({"artifacts": {"weights": artifact_record(directory / "model.pt", directory)}}))
    publish(directory, metadata, models=manifest)
    assert {item.relative for item in plan_task(tmp_path, TASK_ID).files} == {
        "metadata.json",
        "models.json",
        "model.pt",
    }


def test_samples_recent_complete_days_and_keeps_source_unchanged(tmp_path):
    source, staged = tmp_path / "source", tmp_path / "staged"
    directory, metadata = source_task(source)
    original = dataset(directory / "dataset.parquet")
    labels = original.select("trade_date").with_row_index("label")
    labels = pl.concat(
        [labels, pl.DataFrame({"label": [original.height], "trade_date": ["20271231"]}, schema=labels.schema)]
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
    identity = snapshot_digest(source, TASK_ID)
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
    assert snapshot_digest(source, TASK_ID) == identity
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
    with pytest.raises(ReplicaBudgetError, match="Non-sampleable"):
        prepare_replica(tmp_path / "source", TASK_ID, tmp_path / "staged", 32 * 1024)


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
        "source_digest": snapshot_digest(tmp_path / "source", TASK_ID),
        "policy_digest": policy_digest(budget),
    }
    assert snapshot_index(remote, frozenset()) == {TASK_ID: expected}
    assert policy_digest(budget + 1) != expected["policy_digest"]
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
def test_old_stock_signal_outputs_are_rejected(tmp_path, role):
    directory, metadata = source_task(tmp_path, "backtest#demo#axon2-core")
    path = directory / f"{role}.parquet"
    path.write_bytes(b"old output")
    publish(directory, metadata, **{role: path})
    with pytest.raises(ValueError, match="Unsupported stock signals format"):
        plan_task(tmp_path, metadata.task_id)
