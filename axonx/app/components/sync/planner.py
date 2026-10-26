"""Select published task outputs and pack complete display replicas."""

from __future__ import annotations

import json
from pathlib import Path

from ....task.models.lifecycle import TaskMetadata
from ....task.storage.workspace import (
    EVENTS_FILE,
    METADATA_FILE,
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
        path = parent / candidate
        if not path.resolve().is_relative_to(directory.resolve()) or any(
            p.is_symlink() for p in (path, *path.parents) if p != directory.parent
        ):
            raise ValueError(f"Artifact path escapes its Task: {relative}")
        name = path.relative_to(directory).as_posix()
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
    files = tuple(task_file(directory / name, name) for name in sorted(paths))
    return TaskPlan(files, sum(item.archived_bytes for item in files), omitted)


def archive_budget(transfer_budget_bytes: int) -> int:
    """Reserve tar padding and worst-case gzip overhead inside the same total budget."""
    return max(0, transfer_budget_bytes - 10240 - max(4096, transfer_budget_bytes // 1024))


def pack_batches(
    plans: dict[str, TaskPlan], budget: int, max_batches: int, *, members: dict[str, set[str]] | None = None
):
    batches: list[list[str]] = []
    rejected: list[str] = []
    current: list[str] = []
    included: set[str] = set()
    used = 0
    for task_id, plan in plans.items():
        if plan.empty:
            continue
        if plan.size > budget:
            rejected.append(task_id)
            continue
        identities = members[task_id] if members is not None else {task_id}
        if current and (used + plan.size > budget or included & identities):
            batches.append(current)
            current, used = [], 0
            included.clear()
        current.append(task_id)
        included.update(identities)
        used += plan.size
    if current:
        batches.append(current)
    deferred = [task_id for batch in batches[max_batches:] for task_id in batch]
    return batches[:max_batches], rejected, deferred
