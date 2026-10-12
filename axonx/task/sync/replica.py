"""Prepare bounded, valid display artifacts without modifying source files."""

from __future__ import annotations

import io
from pathlib import Path

import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq

from ...utils.fs import file_sha256, snapshot_file
from ..storage.replica import DisplayReplica, ReplicaFile
from ..storage.workspace import (
    METADATA_FILE,
    read_entry,
    task_path,
    write_task_metadata,
)
from .errors import ReplicaBudgetError, SnapshotChangedError
from .index import policy_digest, snapshot_digest
from .models import TaskPlan
from .planner import archive_budget, plan_task, task_file

# Full reports, transaction ledgers and reference calendars remain source-complete.
COMPLETE_FILES = {
    "daily.parquet",
    "summary.parquet",
    "orders.parquet",
    "positions.parquet",
    "trades.parquet",
    "calendar.parquet",
}


def _day():
    return pl.col("trade_date").cast(pl.String).str.replace_all("-", "")


class _BudgetWriter(io.BufferedWriter):
    def __init__(self, path: Path, limit: int):
        super().__init__(path.open("wb", buffering=0))
        self.limit = limit

    def write(self, data):
        if self.tell() + len(data) > self.limit:
            raise ReplicaBudgetError("Encoded sample exceeds the remaining transfer budget")
        return super().write(data)


def _write_sample(source: Path, target: Path, dates: list[str], limit: int) -> None:
    parquet = pq.ParquetFile(source)
    groups = []
    column = next(i for i in range(len(parquet.schema)) if parquet.schema.column(i).path == "trade_date")
    for index in range(parquet.metadata.num_row_groups):
        stats = parquet.metadata.row_group(index).column(column).statistics
        if stats is not None and stats.has_min_max:
            lower, upper = str(stats.min).replace("-", ""), str(stats.max).replace("-", "")
            if not any(lower <= day <= upper for day in dates):
                continue
        groups.append(index)
    with (
        _BudgetWriter(target, limit) as stream,
        pq.ParquetWriter(stream, parquet.schema_arrow, compression="zstd") as writer,
    ):
        pending, pending_bytes = [], 0
        for batch in parquet.iter_batches(batch_size=8192, row_groups=groups):
            frame = pl.from_arrow(batch).filter(_day().is_in(dates))
            if frame.height:
                table = frame.to_arrow().cast(parquet.schema_arrow)
                pending.append(table)
                pending_bytes += table.nbytes
                if pending_bytes >= 16 * 1024 * 1024:
                    writer.write_table(pa.concat_tables(pending))
                    pending, pending_bytes = [], 0
        if pending:
            writer.write_table(pa.concat_tables(pending))


def prepare_replica(root: Path, task_id: str, destination: Path, budget: int) -> TaskPlan:
    source = task_path(root, task_id)
    before = plan_task(root, task_id)
    identity = snapshot_digest(root, task_id)
    metadata = read_entry(root, task_id)
    if metadata is None:
        raise SnapshotChangedError(f"Task disappeared: {task_id}")
    destination.mkdir(parents=True, exist_ok=True)
    originals = {item.relative: item for item in before.files if item.relative != METADATA_FILE}
    omitted = {
        name + "/": "upstream input snapshot" for name in ("inputs", "model_snapshot") if (source / name).is_dir()
    }
    sampleable: dict[str, dict[str, int]] = {}
    for name, item in originals.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        snapshot_file(item.path, target)
    source_log = metadata.log_path
    metadata.log_path = ""

    def materialize(dates: list[str] | None, omit_data: bool = False) -> TaskPlan | None:
        files = {}
        remaining = archive_budget(budget) - sum(
            item.archived_bytes for name, item in originals.items() if name not in sampleable
        )
        for name, item in originals.items():
            target = destination / name
            sampled = dates is not None and name in sampleable
            if omit_data and name in sampleable:
                target.unlink(missing_ok=True)
                omitted[name] = "latest complete trading day exceeds the transfer budget"
                continue
            rows = source_rows = None
            retained = []
            if sampled:
                # Unlink the staging hard link before writing; never alter the source inode.
                target.unlink(missing_ok=True)
                try:
                    _write_sample(item.path, target, dates, max(0, remaining))
                except ReplicaBudgetError:
                    target.unlink(missing_ok=True)
                    return None
                remaining -= target.stat().st_size
                rows = pq.ParquetFile(target).metadata.num_rows
                source_rows = pq.ParquetFile(item.path).metadata.num_rows
                retained = sorted(set(sampleable[name]) & set(dates))
            files[name] = ReplicaFile(
                size=target.stat().st_size,
                sha256="0" * 64,
                sampled=sampled,
                rows=rows,
                source_rows=source_rows,
                dates=retained,
            )
        metadata.replica = DisplayReplica(
            source_digest=identity,
            policy_digest=policy_digest(budget),
            files=files,
            omitted=dict(omitted),
            source_log_path=source_log,
        )
        write_task_metadata(destination, metadata)
        items = tuple(task_file(destination / name, name) for name in sorted({METADATA_FILE, *files}))
        return TaskPlan(items, sum(item.archived_bytes for item in items))

    limit = archive_budget(budget)
    prepared = materialize(None)
    if prepared.size > limit:
        for name, item in originals.items():
            if (
                item.path.suffix != ".parquet"
                or item.path.name in COMPLETE_FILES
                or item.path.stem.endswith(("_orders", "_positions", "_trades", "_summary"))
            ):
                continue
            if "trade_date" not in pl.read_parquet_schema(item.path):
                continue
            counts = pl.scan_parquet(item.path).select(_day()).group_by("trade_date").len().collect()
            days = dict(counts.iter_rows())
            if days and all(isinstance(day, str) and len(day) == 8 and day.isdigit() for day in days):
                sampleable[name] = days
        if not sampleable:
            raise ReplicaBudgetError(f"Non-sampleable outputs exceed the transfer budget: {task_id}")
        primary = max(sampleable, key=lambda name: originals[name].size)
        latest = max(sampleable[primary])
        estimates: dict[str, float] = {}
        for name, counts in sampleable.items():
            bytes_per_row = originals[name].size / sum(counts.values())
            for day, rows in counts.items():
                if day <= latest:
                    estimates[day] = estimates.get(day, 0) + bytes_per_row * rows
        available = limit - sum(item.archived_bytes for name, item in originals.items() if name not in sampleable)
        dates, estimated = [], 0.0
        for day in sorted(estimates, reverse=True):
            if dates and estimated + estimates[day] > available * 0.8:
                break
            dates.append(day)
            estimated += estimates[day]
        dates.sort()
        # Estimate once, then shrink only when actual encoding exceeds the budget.
        while dates:
            prepared = materialize(dates)
            if prepared is not None and prepared.size <= limit:
                break
            dates = dates[len(dates) // 2 :] if len(dates) > 1 else []
        if not dates:
            prepared = materialize([], omit_data=True)
        if prepared is None or prepared.size > limit:
            raise ReplicaBudgetError(f"Required records and non-sampleable outputs exceed the budget: {task_id}")
    if before != plan_task(root, task_id):
        raise SnapshotChangedError(f"Task changed while preparing display artifacts: {task_id}")
    for name, record in metadata.replica.files.items():
        record.sha256 = file_sha256(destination / name)
    if before != plan_task(root, task_id):
        raise SnapshotChangedError(f"Task changed during replica verification: {task_id}")
    write_task_metadata(destination, metadata)
    items = tuple(task_file(destination / item.relative, item.relative) for item in prepared.files)
    prepared = TaskPlan(items, sum(item.archived_bytes for item in items))
    if prepared.size > limit:
        raise ReplicaBudgetError(f"Replica manifest exceeds the transfer budget: {task_id}")
    return prepared
