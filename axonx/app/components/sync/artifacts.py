"""Discover published artifacts, identify sources, validate replicas and sample complete days."""

from __future__ import annotations

import io
import json
from pathlib import Path, PurePosixPath

import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq

from ....task.models.artifacts import fingerprint
from ....task.models.lifecycle import TaskMetadata
from ....task.storage.logs import TaskLogReader
from ....task.storage.workspace import EVENTS_FILE, METADATA_FILE, read_entry, task_path
from .models import ReplicaBudgetError, SnapshotChangedError, TaskPlan


def artifact_path(directory: Path, name: str) -> Path:
    """Require one canonical, non-symlink file path inside its Task directory."""
    relative = PurePosixPath(name)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts or relative.as_posix() != name:
        raise ValueError(f"Invalid replica path: {name}")
    path = directory / name
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError(f"Invalid replica path: {name}")
    return path


def plan_task(root: Path, task_id: str, *, snapshot: TaskMetadata | None = None) -> TaskPlan:
    """Only published outputs and their manifest dependencies belong to a replica."""
    directory = task_path(root, task_id)
    metadata = snapshot or read_entry(root, task_id)
    if metadata is None or (snapshot is None and not metadata.state.is_terminal) or metadata.replica is not None:
        raise SnapshotChangedError(f"Task is not a terminal source snapshot: {task_id}")
    paths = {METADATA_FILE}
    if (directory / EVENTS_FILE).is_file():
        paths.add(EVENTS_FILE)
    visited: set[str] = set()
    omitted = {}

    def references(value):
        if isinstance(value, dict):
            # Only publication containers own files. Protocol provenance and
            # parent Task summaries may contain paths belonging to other Tasks.
            for role, record in value.get("artifacts", {}).items():
                if snapshot is not None and (
                    role
                    in {
                        "features",
                        "input_features",
                        "feature_protocol",
                        "model_manifest",
                    }
                    or role.startswith(("model_", "source_", "debug_"))
                ):
                    continue
                yield record["path"]
            if value.get("previous"):
                yield value["previous"]["path"]
            for key in ("commits", "comparisons"):
                for item in value.get(key, []):
                    yield from references(item)

    def include(relative: str, parent: Path = directory):
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError(f"Artifact path must stay inside its Task: {relative}")
        name = (parent / candidate).relative_to(directory).as_posix()
        path = artifact_path(directory, name)
        if name.split("/", 1)[0] in {"inputs", "model_snapshot"}:
            return
        if not path.is_file():
            omitted[name] = "published artifact is missing"
            return
        paths.add(name)
        if path.suffix == ".json" and name not in visited:
            visited.add(name)
            publication = json.loads(path.read_text(encoding="utf-8"))
            # Model collections are file-relative; online publications are Task-relative.
            base = path.parent if isinstance(publication, dict) and "members" in publication else directory
            for reference in references(publication):
                pending.append((reference, base))

    # Frozen online histories can span thousands of revisions. Traverse their
    # manifest dependencies iteratively rather than using the Python call stack.
    pending = [(reference, directory) for reference in references(metadata.output_params)]
    while pending:
        relative, parent = pending.pop()
        include(relative, parent)
    return TaskPlan.capture(directory, paths, omitted=omitted)


def policy_revision(budget: int) -> str:
    return f"display-replica-3:{budget}:latest-whole-days"


def source_revision(
    root: Path,
    task_id: str,
    *,
    snapshot: TaskMetadata | None = None,
    logs: TaskLogReader | None = None,
    plan: TaskPlan | None = None,
) -> str:
    """Identify publications from Task start time and file metadata without reading payloads."""
    plan = plan if plan is not None else plan_task(root, task_id, snapshot=snapshot)
    metadata = snapshot or read_entry(root, task_id)
    if metadata is None:
        raise SnapshotChangedError(f"Task disappeared during reconciliation: {task_id}")
    files = [(item.relative, item.size, item.modified_ns) for item in plan.files]
    log = logs.path(metadata) if logs is not None else None
    if log is not None and logs.is_task_log(log) and log.is_file():
        stat = log.stat()
        files.append(("display/log.log", stat.st_size, stat.st_mtime_ns))
    return fingerprint([metadata.started_at.isoformat(), files])


def verify_replica(root: Path, task_id: str, *, metadata: TaskMetadata | None = None) -> None:
    metadata = metadata or read_entry(root, task_id)
    if (
        metadata is None
        or metadata.replica is None
        or (not metadata.state.is_terminal and metadata.replica.snapshot is None)
    ):
        raise ValueError(f"Task is not a display replica: {task_id}")
    directory = task_path(root, task_id)
    actual = {p.relative_to(directory).as_posix() for p in directory.rglob("*") if p.is_file()}
    if actual != {"metadata.json", *metadata.replica.files}:
        raise ValueError(f"Replica file manifest differs from its directory: {task_id}")
    log = metadata.replica.log
    if log is not None:
        record = metadata.replica.files.get(log.path)
        if record is None or log.end - log.start != record.size:
            raise ValueError(f"Invalid replica log range: {task_id}")
    for name, record in metadata.replica.files.items():
        path = artifact_path(directory, name)
        if name == METADATA_FILE:
            raise ValueError(f"Invalid replica path: {name}")
        if path.stat().st_size != record.size:
            raise ValueError(f"Replica artifact size mismatch: {task_id}/{name}")


def trade_day():
    return pl.col("trade_date").cast(pl.String).str.replace_all("-", "")


class _BudgetWriter(io.BufferedWriter):
    def __init__(self, path: Path, limit: int):
        super().__init__(path.open("wb", buffering=0))
        self.limit = limit

    def write(self, data):
        if self.tell() + len(data) > self.limit:
            raise ReplicaBudgetError("Encoded sample exceeds the remaining transfer budget")
        return super().write(data)


def write_sample(source: Path, target: Path, dates: list[str], limit: int) -> None:
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
            frame = pl.from_arrow(batch).filter(trade_day().is_in(dates))
            if frame.height:
                table = frame.to_arrow().cast(parquet.schema_arrow)
                pending.append(table)
                pending_bytes += table.nbytes
                if pending_bytes >= 16 * 1024 * 1024:
                    writer.write_table(pa.concat_tables(pending))
                    pending, pending_bytes = [], 0
        if pending:
            writer.write_table(pa.concat_tables(pending))
