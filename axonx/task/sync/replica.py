"""Prepare bounded, valid display artifacts without modifying source files."""

from __future__ import annotations

import socket
import time
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import pyarrow.parquet as pq

from ...utils.fs import file_sha256, snapshot_file
from ..schemas.lifecycle import TaskMetadata, current_children
from ..schemas.protocol import fingerprint
from ..schemas.replica import DisplayReplica, LiveSnapshot, ReplicaFile, ReplicaLog
from ..storage.logs import TaskLogReader
from ..storage.workspace import METADATA_FILE, EVENTS_FILE, read_entry, task_path, write_task_metadata
from .errors import ReplicaBudgetError, SnapshotChangedError
from .index import policy_digest, snapshot_digest
from .models import TaskPlan
from .planner import archive_budget, plan_task, task_file
from .sampling import trade_day, write_sample

# Full reports, transaction ledgers and reference calendars remain source-complete.
COMPLETE_FILES = {
    "daily.parquet",
    "summary.parquet",
    "orders.parquet",
    "positions.parquet",
    "trades.parquet",
    "calendar.parquet",
}


def prepare_replica(
    root: Path,
    task_id: str,
    destination: Path,
    budget: int,
    *,
    snapshot: LiveSnapshot | None = None,
    metadata: TaskMetadata | None = None,
    logs: TaskLogReader | None = None,
    remote: dict | None = None,
) -> TaskPlan:
    source = task_path(root, task_id)
    before = plan_task(root, task_id, snapshot=metadata if snapshot else None)
    metadata = metadata or read_entry(root, task_id)
    if metadata is None:
        raise SnapshotChangedError(f"Task disappeared: {task_id}")
    source_metadata = metadata.model_dump(mode="json")
    identity = snapshot_digest(root, task_id) if snapshot is None else fingerprint(source_metadata)
    destination.mkdir(parents=True, exist_ok=True)
    originals = {
        item.relative: item
        for item in before.files
        if item.relative != METADATA_FILE and not (snapshot and item.relative == EVENTS_FILE)
    }
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
    metadata.pid = None
    log = None
    if snapshot and logs:
        path = logs.path(TaskMetadata.model_validate(source_metadata))
        if path is not None and logs.is_task_log(path) and path.is_file():
            with path.open("rb") as stream:
                end = stream.seek(0, 2)
                start = max(0, end - 1024 * 1024)
                stream.seek(start)
                content = stream.read(end - start)
            if len(content) != end - start:
                raise SnapshotChangedError(f"Source log rotated during capture: {task_id}")
            name = "display/log.log"
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            originals[name] = task_file(target, name)
            log = ReplicaLog(path=name, start=start, end=end)

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
                    write_sample(item.path, target, dates, max(0, remaining))
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
            snapshot=snapshot,
            log=log,
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
            counts = pl.scan_parquet(item.path).select(trade_day()).group_by("trade_date").len().collect()
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

    def check_source():
        current = read_entry(root, task_id)
        if current is None or current.run_id != metadata.run_id:
            raise SnapshotChangedError(f"Task Run changed during capture: {task_id}")
        if snapshot is None and before != plan_task(root, task_id):
            raise SnapshotChangedError(f"Task changed during replica verification: {task_id}")
        for item in before.files:
            if item.relative not in {METADATA_FILE, EVENTS_FILE} and task_file(item.path, item.relative) != item:
                raise SnapshotChangedError(f"Published artifact changed during capture: {item.path}")

    check_source()
    for name, record in metadata.replica.files.items():
        record.sha256 = file_sha256(destination / name)
    check_source()
    if snapshot:
        metadata.replica.source_digest = fingerprint(
            {
                "metadata": source_metadata,
                "files": {name: record.sha256 for name, record in metadata.replica.files.items()},
                "log": log.model_dump(mode="json") if log else None,
            }
        )
    write_task_metadata(destination, metadata)
    items = tuple(task_file(destination / item.relative, item.relative) for item in prepared.files)
    prepared = TaskPlan(items, sum(item.archived_bytes for item in items))
    if prepared.size > limit:
        raise ReplicaBudgetError(f"Replica manifest exceeds the transfer budget: {task_id}")
    if snapshot and remote and remote.get("run_id") == metadata.run_id:
        for name, record in metadata.replica.files.items():
            if remote.get("files", {}).get(name) == record.sha256:
                (destination / name).unlink()
        items = tuple(
            task_file(path, path.relative_to(destination).as_posix())
            for path in sorted(destination.rglob("*"))
            if path.is_file()
        )
        # Reserve the hydrated size when packing multiple delta groups together.
        prepared = TaskPlan(items, prepared.size)
    return prepared


def task_group(root: Path, task_id: str) -> dict:
    """Pin children by Run ID; never silently substitute a newer named child."""
    result = {}

    def visit(identity, run_id=None):
        status = read_entry(root, identity)
        if status is None or status.replica is not None or (run_id is not None and status.run_id != run_id):
            raise SnapshotChangedError(f"Live source Run is unavailable: {identity}/{run_id}")
        previous = result.get(identity)
        if previous is not None:
            if previous.run_id != status.run_id:
                raise SnapshotChangedError(f"Conflicting child Runs: {identity}")
            return
        result[identity] = status
        for child in current_children(status):
            if child.task_id:
                visit(child.task_id, child.run_id)

    visit(task_id)
    return result


def prepare_group(
    root: Path,
    task_id: str,
    staging: Path,
    budget: int,
    logs: TaskLogReader,
    remote: dict,
) -> dict[str, TaskPlan]:
    group = task_group(root, task_id)
    snapshot = LiveSnapshot(
        source_id=fingerprint({"host": socket.gethostname(), "workspace": str(root.resolve())}),
        root_task_id=task_id,
        root_run_id=group[task_id].run_id,
        captured_at=datetime.now(UTC),
        revision=time.time_ns(),
    )
    plans = {}
    unchanged = True
    for identity, status in group.items():
        destination = task_path(staging, identity)
        plans[identity] = prepare_replica(
            root,
            identity,
            destination,
            budget,
            snapshot=snapshot,
            metadata=status,
            logs=logs,
            remote=remote.get(identity),
        )
        record = read_entry(staging, identity)
        unchanged &= status.state.is_terminal and all(
            remote.get(identity, {}).get(key) == getattr(record.replica, key)
            for key in ("source_digest", "policy_digest")
        )
    if sum(plan.size for plan in plans.values()) > archive_budget(budget):
        raise ReplicaBudgetError(f"Task group exceeds the transfer budget: {task_id}")
    for identity, status in group.items():
        current = read_entry(root, identity)
        if current is None or current.run_id != status.run_id:
            raise SnapshotChangedError(f"Task Run changed during capture: {identity}")
    return {} if unchanged else plans
