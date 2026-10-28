"""Prepare bounded, valid display artifacts without modifying source files."""

from __future__ import annotations

import socket
import time
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import pyarrow.parquet as pq

from ....task.models.artifacts import fingerprint
from ....task.models.lifecycle import (
    DisplayReplica,
    LiveSnapshot,
    ReplicaFile,
    ReplicaLog,
    TaskMetadata,
)
from ....task.storage.files import snapshot_file
from ....task.storage.logs import TaskLogReader
from ....task.storage.workspace import (
    EVENTS_FILE,
    METADATA_FILE,
    read_entry,
    task_path,
    write_task_metadata,
)
from .archive import archive_budget
from .artifacts import plan_task, policy_revision, source_revision, trade_day, write_sample
from .models import ReplicaBudgetError, SnapshotChangedError, TaskFile, TaskPlan, archived_bytes

# Full reports, transaction ledgers and reference calendars remain source-complete.
COMPLETE_FILES = {
    "daily.parquet",
    "summary.parquet",
    "orders.parquet",
    "positions.parquet",
    "trades.parquet",
    "calendar.parquet",
}


class ReplicaBuilder:
    """Prepare one bounded replica while keeping capture, sampling and verification state together."""

    def __init__(
        self,
        root: Path,
        task_id: str,
        destination: Path,
        budget: int,
        logs: TaskLogReader | None = None,
        *,
        snapshot: LiveSnapshot | None = None,
        metadata: TaskMetadata | None = None,
        remote: dict | None = None,
    ) -> None:
        self.root = root
        self.task_id = task_id
        self.destination = destination
        self.budget = budget
        self.logs = logs
        self.snapshot = snapshot
        self.metadata = metadata.model_copy(deep=True) if metadata is not None else None
        self.remote = remote
        self.source = task_path(root, task_id)
        self.before: TaskPlan | None = None
        self.source_log_path = ""
        self.log_path: Path | None = None
        self.identity = ""
        self.originals: dict[str, TaskFile] = {}
        self.omitted: dict[str, str] = {}
        self.sampleable: dict[str, dict[str, int]] = {}
        self.log: ReplicaLog | None = None
        self.log_revision = ""

    def prepare(self) -> TaskPlan:
        """Capture, bound and verify one source snapshot before returning its archive plan."""
        self.before = plan_task(self.root, self.task_id, snapshot=self.metadata if self.snapshot else None)
        self.metadata = self.metadata or read_entry(self.root, self.task_id)
        if self.metadata is None:
            raise SnapshotChangedError(f"Task disappeared: {self.task_id}")
        self.source_log_path = self.metadata.log_path
        self.log_path = self.logs.path(self.metadata) if self.logs else None
        self.identity = source_revision(
            self.root,
            self.task_id,
            snapshot=self.metadata if self.snapshot else None,
            logs=self.logs if self.snapshot else None,
            plan=self.before,
        )
        self.destination.mkdir(parents=True, exist_ok=True)
        if (
            self.snapshot
            and self.remote
            and (self.remote.get("started_at") == self.metadata.started_at.isoformat())
            and (self.remote.get("source_revision") == self.identity)
            and (self.remote.get("policy_revision") == policy_revision(self.budget))
        ):
            prepared = self._refresh_snapshot()
            self._check_source()
            if prepared.size > archive_budget(self.budget):
                raise ReplicaBudgetError(f"Replica manifest exceeds the transfer budget: {self.task_id}")
            return prepared
        self.originals = {
            item.relative: item
            for item in self.before.files
            if item.relative != METADATA_FILE and (not (self.snapshot and item.relative == EVENTS_FILE))
        }
        self.omitted = dict(self.before.omitted)
        self.omitted.update(
            {
                name + "/": "upstream input snapshot"
                for name in ("inputs", "model_snapshot")
                if (self.source / name).is_dir()
            }
        )
        for name, item in self.originals.items():
            target = self.destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            snapshot_file(item.path, target)
        self.metadata.log_path = ""
        self._capture_log()
        limit = archive_budget(self.budget)
        prepared = self._fit_budget(limit)
        self._check_source()
        if self.snapshot and self.remote and (self.remote.get("started_at") == self.metadata.started_at.isoformat()):
            unchanged = {
                name
                for name, record in self.metadata.replica.files.items()
                if self.remote.get("files", {}).get(name) == record.model_dump(mode="json")
            }
            for name in unchanged:
                (self.destination / name).unlink()
            # Delta archives reserve their hydrated size during batch packing.
            prepared = TaskPlan(tuple(item for item in prepared.files if item.relative not in unchanged), prepared.size)
        return prepared

    def _refresh_snapshot(self) -> TaskPlan:
        """Refresh metadata while reserving the remote publication's hydrated size."""
        self.metadata.log_path = ""
        self.metadata.replica = DisplayReplica.model_validate(
            {key: value for key, value in self.remote.items() if key != "started_at"}
        )
        self.metadata.replica.snapshot = self.snapshot
        write_task_metadata(self.destination, self.metadata)
        item = TaskFile.capture(self.destination / METADATA_FILE, METADATA_FILE)
        return TaskPlan(
            (item,),
            item.archived_bytes + sum(archived_bytes(record.size) for record in self.metadata.replica.files.values()),
        )

    def _capture_log(self) -> None:
        """Capture one bounded tail and retain its exact byte range."""
        if self.logs:
            path = self.log_path
            if path is not None and self.logs.is_task_log(path) and path.is_file():
                with path.open("rb") as stream:
                    end = stream.seek(0, 2)
                    start = max(0, end - min(1024 * 1024, archive_budget(self.budget) // 2))
                    stream.seek(start)
                    content = stream.read(end - start)
                if len(content) != end - start:
                    raise SnapshotChangedError(f"Source log rotated during capture: {self.task_id}")
                name = "display/log.log"
                target = self.destination / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
                self.originals[name] = TaskFile.capture(target, name)
                self.log_revision = f"{start}:{end}:{path.stat().st_mtime_ns}"
                self.log = ReplicaLog(path=name, start=start, end=end)

    def _fit_budget(self, limit: int) -> TaskPlan:
        """Keep complete trading days, then omit artifacts explicitly if needed."""
        prepared = self._materialize(None)
        if prepared.size > limit:
            for name, item in self.originals.items():
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
                if days and all((isinstance(day, str) and len(day) == 8 and day.isdigit() for day in days)):
                    self.sampleable[name] = days
            latest = (
                max(self.sampleable[max(self.sampleable, key=lambda name: self.originals[name].size)])
                if self.sampleable
                else ""
            )
            estimates: dict[str, float] = {}
            for name, counts in self.sampleable.items():
                bytes_per_row = self.originals[name].size / sum(counts.values())
                for day, rows in counts.items():
                    if day <= latest:
                        estimates[day] = estimates.get(day, 0) + bytes_per_row * rows
            available = limit - sum(
                (item.archived_bytes for name, item in self.originals.items() if name not in self.sampleable)
            )
            dates, estimated = ([], 0.0)
            for day in sorted(estimates, reverse=True):
                if dates and estimated + estimates[day] > available * 0.8:
                    break
                dates.append(day)
                estimated += estimates[day]
            dates.sort()
            # Encode once from an estimate, then shrink complete days only as needed.
            while dates:
                prepared = self._materialize(dates)
                if prepared is not None and prepared.size <= limit:
                    break
                dates = dates[len(dates) // 2 :] if len(dates) > 1 else []
            if not dates:
                prepared = self._materialize([], omit_data=True)
            # Non-sampleable artifacts are omitted explicitly, never truncated.
            for name in sorted(
                self.originals, key=lambda name: (name == "display/log.log", -self.originals[name].size)
            ):
                if prepared is not None and prepared.size <= limit:
                    break
                self.originals.pop(name)
                if self.log is not None and name == self.log.path:
                    self.log = None
                (self.destination / name).unlink(missing_ok=True)
                self.omitted[name] = "transfer budget"
                prepared = self._materialize([], omit_data=True)
            if prepared is None or prepared.size > limit:
                raise ReplicaBudgetError(f"Task metadata exceeds the transfer budget: {self.task_id}")
        return prepared

    def _materialize(self, dates: list[str] | None, omit_data: bool = False) -> TaskPlan | None:
        """Write a self-contained manifest while accounting for the complete encoded payload."""
        files = {}
        remaining = archive_budget(self.budget) - sum(
            (item.archived_bytes for name, item in self.originals.items() if name not in self.sampleable)
        )
        for name, item in self.originals.items():
            target = self.destination / name
            sampled = dates is not None and name in self.sampleable
            if omit_data and name in self.sampleable:
                target.unlink(missing_ok=True)
                self.omitted[name] = "latest complete trading day exceeds the transfer budget"
                continue
            rows = source_rows = None
            retained = []
            if sampled:
                # Staging may share the source inode; unlink before rewriting the sample.
                target.unlink(missing_ok=True)
                try:
                    write_sample(item.path, target, dates, max(0, remaining))
                except ReplicaBudgetError:
                    target.unlink(missing_ok=True)
                    return None
                remaining -= target.stat().st_size
                rows = pq.ParquetFile(target).metadata.num_rows
                source_rows = pq.ParquetFile(item.path).metadata.num_rows
                retained = sorted(set(self.sampleable[name]) & set(dates))
            files[name] = ReplicaFile(
                size=target.stat().st_size,
                revision=(
                    self.log_revision
                    if self.log is not None and name == self.log.path
                    else f"{item.size}:{item.modified_ns}:{(dates if sampled else None)}"
                ),
                sampled=sampled,
                rows=rows,
                source_rows=source_rows,
                dates=retained,
            )
        self.metadata.replica = DisplayReplica(
            source_revision=self.identity,
            policy_revision=policy_revision(self.budget),
            files=files,
            omitted=dict(self.omitted),
            source_log_path=self.source_log_path,
            snapshot=self.snapshot,
            log=self.log,
        )
        write_task_metadata(self.destination, self.metadata)
        return TaskPlan.capture(self.destination, {METADATA_FILE, *files})

    def _check_source(self) -> None:
        """Reject replaced executions or artifacts changed during capture."""
        current = read_entry(self.root, self.task_id)
        if current is None or current.started_at != self.metadata.started_at:
            raise SnapshotChangedError(f"Task restarted during capture: {self.task_id}")
        if self.snapshot is None and self.before != plan_task(self.root, self.task_id):
            raise SnapshotChangedError(f"Task changed during replica verification: {self.task_id}")
        for item in self.before.files:
            if item.relative not in {METADATA_FILE, EVENTS_FILE} and not item.matches(item.path.stat()):
                raise SnapshotChangedError(f"Published artifact changed during capture: {item.path}")


def task_group(root: Path, task_id: str) -> dict:
    """Check child start times; never silently substitute a restarted child."""
    result = {}

    pending = [(task_id, None)]
    while pending:
        identity, started_at = pending.pop()
        status = read_entry(root, identity)
        if status is None or status.replica is not None or (started_at is not None and status.started_at != started_at):
            raise SnapshotChangedError(f"Live source Task is unavailable: {identity}/{started_at}")
        previous = result.get(identity)
        if previous is not None:
            if previous.started_at != status.started_at:
                raise SnapshotChangedError(f"Conflicting child start times: {identity}")
            continue
        result[identity] = status
        pending.extend(
            reversed(
                [
                    (child.child_task_id, child.started_at)
                    for child in status.current_children()
                    if child.child_task_id and child.started_at is not None
                ]
            )
        )

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
    member_budget = archive_budget(budget) // len(group)
    policy = policy_revision(member_budget)
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
    for identity, status in group.items():
        destination = task_path(staging, identity)
        plans[identity] = ReplicaBuilder(
            root,
            identity,
            destination,
            member_budget,
            snapshot=snapshot,
            metadata=status,
            logs=logs,
            remote=remote.get(identity),
        ).prepare()
    if sum(plan.size for plan in plans.values()) > archive_budget(budget):
        raise ReplicaBudgetError(f"Task group exceeds the transfer budget: {task_id}")
    for identity, status in group.items():
        current = read_entry(root, identity)
        if current is None or current.started_at != status.started_at:
            raise SnapshotChangedError(f"Task restarted during capture: {identity}")
    return plans
