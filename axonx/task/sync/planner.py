"""Select published task outputs and pack complete display replicas."""

from __future__ import annotations

import json
from pathlib import Path

from ..protocol import STOCK_SIGNALS_FORMAT
from ..storage.workspace import (
    EVENTS_FILE,
    METADATA_FILE,
    TaskMetadata,
    read_entry,
    task_path,
)
from .errors import SnapshotChangedError
from .models import TaskFile, TaskPlan


def task_file(path: Path, relative: str) -> TaskFile:
    stat = path.stat()
    return TaskFile(path, relative, stat.st_size, stat.st_mtime_ns, stat.st_ino)


def plan_task(root: Path, task_id: str, *, snapshot: TaskMetadata | None = None) -> TaskPlan:
    """Only published outputs and their manifest dependencies belong to a replica."""
    directory = task_path(root, task_id)
    metadata = snapshot or read_entry(root, task_id)
    if metadata is None or (snapshot is None and not metadata.state.is_terminal) or metadata.replica is not None:
        raise SnapshotChangedError(f"Task is not a terminal source snapshot: {task_id}")
    paths = {METADATA_FILE}
    artifacts = metadata.output_params.get("artifacts", {})
    if metadata.task_type.value == "backtest" and (
        "targets" in artifacts
        or "signals" in artifacts
        and metadata.output_params.get("signals_format") != STOCK_SIGNALS_FORMAT
    ):
        raise ValueError("Unsupported stock signals format; regenerate backtest outputs")
    if (directory / EVENTS_FILE).is_file():
        paths.add(EVENTS_FILE)
    visited: set[str] = set()

    def references(value):
        if isinstance(value, dict):
            if isinstance(value.get("path"), str) and "sha256" in value:
                yield value["path"]
            for role, nested in value.items():
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
                yield from references(nested)
        elif isinstance(value, list):
            for nested in value:
                yield from references(nested)

    def include(relative: str, parent: Path = directory):
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError(f"Artifact path must stay inside its Task: {relative}")
        path = parent / candidate
        if not path.is_file() and parent != directory:
            path = directory / candidate
        if not path.resolve().is_relative_to(directory.resolve()) or any(
            p.is_symlink() for p in (path, *path.parents) if p != directory.parent
        ):
            raise ValueError(f"Artifact path escapes its Task: {relative}")
        name = path.relative_to(directory).as_posix()
        if name.split("/", 1)[0] in {"inputs", "model_snapshot"}:
            return
        if not path.is_file():
            raise SnapshotChangedError(f"Published artifact is missing: {path}")
        paths.add(name)
        if path.suffix == ".json" and name not in visited:
            visited.add(name)
            for reference in references(json.loads(path.read_text(encoding="utf-8"))):
                # Online records use Task-relative paths; model manifests use file-relative paths.
                base = directory if (directory / reference).is_file() else path.parent
                include(reference, base)

    for reference in references(metadata.output_params):
        include(reference)
    files = tuple(task_file(directory / name, name) for name in sorted(paths))
    return TaskPlan(files, sum(item.archived_bytes for item in files))


def archive_budget(transfer_budget_bytes: int) -> int:
    """Reserve tar padding and worst-case gzip overhead inside the same total budget."""
    return max(0, transfer_budget_bytes - 10240 - max(4096, transfer_budget_bytes // 1024))


def pack_batches(plans: dict[str, TaskPlan], budget: int, max_batches: int):
    batches: list[list[str]] = []
    rejected: list[str] = []
    current: list[str] = []
    used = 0
    for task_id, plan in plans.items():
        if plan.empty:
            continue
        if plan.size > budget:
            rejected.append(task_id)
            continue
        if current and used + plan.size > budget:
            batches.append(current)
            current, used = [], 0
        current.append(task_id)
        used += plan.size
    if current:
        batches.append(current)
    deferred = [task_id for batch in batches[max_batches:] for task_id in batch]
    return batches[:max_batches], rejected, deferred
