"""Prepare bounded, valid display artifacts without modifying source files."""

from __future__ import annotations

import socket
import time
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import pyarrow.parquet as pq

from ..storage.files import snapshot_file
from ..models.artifacts import fingerprint
from ..models.lifecycle import (
    DisplayReplica,
    LiveSnapshot,
    ReplicaFile,
    ReplicaLog,
    TaskMetadata,
    current_children,
)
from ..storage.logs import TaskLogReader
from ..storage.workspace import (
    EVENTS_FILE,
    METADATA_FILE,
    read_entry,
    task_path,
    write_task_metadata,
)
from .errors import ReplicaBudgetError, SnapshotChangedError
from .index import policy_revision, source_revision
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


def _refresh_snapshot(metadata, snapshot, remote, destination):
    """Refresh only metadata when the complete remote publication is unchanged."""
    metadata.log_path = ""
    metadata.replica = DisplayReplica.model_validate(
        {key: value for key, value in remote.items() if key != "started_at"}
    )
    metadata.replica.snapshot = snapshot
    write_task_metadata(destination, metadata)
    item = task_file(destination / METADATA_FILE, METADATA_FILE)
    return TaskPlan(
        (item,),
        item.archived_bytes
        + sum(512 + ((record.size + 511) // 512) * 512 for record in metadata.replica.files.values()),
    )


def prepare_replica(
    root: Path,
    task_id: str,
    destination: Path,
    budget: int,
    logs: TaskLogReader | None = None,
    *,
    snapshot: LiveSnapshot | None = None,
    metadata: TaskMetadata | None = None,
    remote: dict | None = None,
) -> TaskPlan:
    source = task_path(root, task_id)
    before = plan_task(root, task_id, snapshot=metadata if snapshot else None)
    metadata = metadata or read_entry(root, task_id)
    if metadata is None:
        raise SnapshotChangedError(f"Task disappeared: {task_id}")
    source_log_path = metadata.log_path
    log_path = logs.path(metadata) if logs else None
    identity = source_revision(
        root,
        task_id,
        snapshot=metadata if snapshot else None,
        logs=logs if snapshot else None,
    )
    destination.mkdir(parents=True, exist_ok=True)
    if (
        snapshot
        and remote
        and remote.get("started_at") == metadata.started_at.isoformat()
        and remote.get("source_revision") == identity
        and remote.get("policy_revision") == policy_revision(budget)
    ):
        return _refresh_snapshot(metadata, snapshot, remote, destination)
    originals = {
        item.relative: item
        for item in before.files
        if item.relative != METADATA_FILE and not (snapshot and item.relative == EVENTS_FILE)
    }
    omitted = dict(before.omitted)
    omitted.update(
        {name + "/": "upstream input snapshot" for name in ("inputs", "model_snapshot") if (source / name).is_dir()}
    )
    sampleable: dict[str, dict[str, int]] = {}
    for name, item in originals.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        snapshot_file(item.path, target)
    metadata.log_path = ""
    log = None
    log_revision = ""
    if logs:
        path = log_path
        if path is not None and logs.is_task_log(path) and path.is_file():
            with path.open("rb") as stream:
                end = stream.seek(0, 2)
                start = max(0, end - min(1024 * 1024, archive_budget(budget) // 2))
                stream.seek(start)
                content = stream.read(end - start)
            if len(content) != end - start:
                raise SnapshotChangedError(f"Source log rotated during capture: {task_id}")
            name = "display/log.log"
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            originals[name] = task_file(target, name)
            log_revision = f"{start}:{end}:{path.stat().st_mtime_ns}"
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
                revision=(
                    log_revision
                    if log is not None and name == log.path
                    else f"{item.size}:{item.modified_ns}:{dates if sampled else None}"
                ),
                sampled=sampled,
                rows=rows,
                source_rows=source_rows,
                dates=retained,
            )
        metadata.replica = DisplayReplica(
            source_revision=identity,
            policy_revision=policy_revision(budget),
            files=files,
            omitted=dict(omitted),
            source_log_path=source_log_path,
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
        latest = max(sampleable[max(sampleable, key=lambda name: originals[name].size)]) if sampleable else ""
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
        # Metadata and bounded logs remain useful even when data cannot fit.
        # Never truncate a non-sampleable file: omit it explicitly instead.
        for name in sorted(
            originals,
            key=lambda name: (name == "display/log.log", -originals[name].size),
        ):
            if prepared is not None and prepared.size <= limit:
                break
            originals.pop(name)
            if log is not None and name == log.path:
                log = None
            (destination / name).unlink(missing_ok=True)
            omitted[name] = "transfer budget"
            prepared = materialize([], omit_data=True)
        if prepared is None or prepared.size > limit:
            raise ReplicaBudgetError(f"Task metadata exceeds the transfer budget: {task_id}")

    def check_source():
        current = read_entry(root, task_id)
        if current is None or current.started_at != metadata.started_at:
            raise SnapshotChangedError(f"Task restarted during capture: {task_id}")
        if snapshot is None and before != plan_task(root, task_id):
            raise SnapshotChangedError(f"Task changed during replica verification: {task_id}")
        for item in before.files:
            if item.relative not in {METADATA_FILE, EVENTS_FILE} and task_file(item.path, item.relative) != item:
                raise SnapshotChangedError(f"Published artifact changed during capture: {item.path}")

    check_source()
    write_task_metadata(destination, metadata)
    items = tuple(task_file(destination / item.relative, item.relative) for item in prepared.files)
    prepared = TaskPlan(items, sum(item.archived_bytes for item in items))
    if prepared.size > limit:
        raise ReplicaBudgetError(f"Replica manifest exceeds the transfer budget: {task_id}")
    if snapshot and remote and remote.get("started_at") == metadata.started_at.isoformat():
        for name, record in metadata.replica.files.items():
            if remote.get("files", {}).get(name) == record.model_dump(mode="json"):
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
    """Check child start times; never silently substitute a restarted child."""
    result = {}

    def visit(identity, started_at=None):
        status = read_entry(root, identity)
        if status is None or status.replica is not None or (started_at is not None and status.started_at != started_at):
            raise SnapshotChangedError(f"Live source Task is unavailable: {identity}/{started_at}")
        previous = result.get(identity)
        if previous is not None:
            if previous.started_at != status.started_at:
                raise SnapshotChangedError(f"Conflicting child start times: {identity}")
            return
        result[identity] = status
        for child in current_children(status):
            if child.task_id and child.started_at is not None:
                visit(child.task_id, child.started_at)

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
    policy = policy_revision(archive_budget(budget) // len(group))
    if all(
        status.state.is_terminal
        and remote.get(identity, {}).get("source_revision")
        == source_revision(root, identity, snapshot=status, logs=logs)
        and remote.get(identity, {}).get("policy_revision") == policy
        for identity, status in group.items()
    ):
        return {}
    snapshot = LiveSnapshot(
        source_id=fingerprint({"host": socket.gethostname(), "workspace": str(root.resolve())}),
        root_task_id=task_id,
        root_started_at=group[task_id].started_at,
        captured_at=datetime.now(UTC),
        revision=time.time_ns(),
    )
    plans = {}
    member_budget = archive_budget(budget) // len(group)
    for identity, status in group.items():
        destination = task_path(staging, identity)
        plans[identity] = prepare_replica(
            root,
            identity,
            destination,
            member_budget,
            snapshot=snapshot,
            metadata=status,
            logs=logs,
            remote=remote.get(identity),
        )
    if sum(plan.size for plan in plans.values()) > archive_budget(budget):
        raise ReplicaBudgetError(f"Task group exceeds the transfer budget: {task_id}")
    for identity, status in group.items():
        current = read_entry(root, identity)
        if current is None or current.started_at != status.started_at:
            raise SnapshotChangedError(f"Task restarted during capture: {identity}")
    return plans
