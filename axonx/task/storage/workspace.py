"""Task directory layout, lifecycle records and read-only metadata scans."""

from __future__ import annotations

import math
import os
import shutil
import stat
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from typing import Any

from ..models.identity import TaskType, task_type_from_id
from ..models.lifecycle import TaskMetadata
from .files import atomic_write_json

#: One workspace directory per producer type holds that type's task directories.
KINDS = tuple(kind.value for kind in TaskType)

PERSISTENT_DIR = "persistent"
METADATA_FILE = "metadata.json"
#: The append-only log a worker writes its status transitions to, so a manager in
#: another process can follow a running task event by event.
EVENTS_FILE = "events.jsonl"
FileVersion = tuple[int, int, int, int]


def task_directory(task_id: str) -> str:
    """Return the workspace-relative ``<task kind>/<task id>`` of a task."""
    return f"{task_type_from_id(task_id).value}/{task_id}"


def task_path(root: Path, task_id: str) -> Path:
    """Return the directory one task owns, validating its ID as a side effect."""
    return root / task_directory(task_id)


def parse_task_directory(path: str) -> TaskType:
    """Read the kind of one workspace-relative ``<task kind>/<task id>``.

    Exactly two parts that agree name one task directory. Everything else is
    refused - a bare task kind names every task of that kind at once, and a path
    below a task directory names one file inside it.
    """
    if not isinstance(path, str):
        raise TypeError("Task directory must be a string")
    parts = PurePosixPath(path).parts
    if len(parts) != 2:
        raise ValueError(f"Task directories are <task kind>/<task id>: {path!r}")
    kind, task_id = parts
    task_type = task_type_from_id(task_id)
    if task_type.value != kind:
        raise ValueError(f"Task directory kind does not match its ID: {path!r}")
    return task_type


def is_task_directory(directory: Path) -> bool:
    """Whether a path is a task directory this process may read or write.

    A directory reached through a symlink is refused twice over: a write through one
    would land outside the workspace, and it would recreate a directory that a
    concurrent delete had just removed. Checks propagate I/O errors other
    than missing directories so callers can retry instead of treating them as gone.
    """
    try:
        return all(stat.S_ISDIR(parent.lstat().st_mode) for parent in (directory.parent, directory))
    except FileNotFoundError:
        return False


def reset_task_directory(directory: Path) -> None:
    """Clear run-owned files while retaining the Task's persistent data."""
    if not is_task_directory(directory):
        raise ValueError(f"Invalid Task directory: {directory}")
    persistent = directory / PERSISTENT_DIR
    if persistent.is_symlink() or (persistent.exists() and not persistent.is_dir()):
        raise ValueError(f"Persistent Task storage must be a regular directory: {persistent}")
    # Keep the terminal record until the disposable files have been removed.
    for path in sorted(directory.iterdir(), key=lambda path: path.name == METADATA_FILE):
        if path.name == PERSISTENT_DIR:
            continue
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()


def read_entry(root: Path, task_id: str) -> TaskMetadata | None:
    """Read one task directory, or None when it holds nothing to index."""
    directory = task_path(root, task_id)
    return read_task_metadata(directory, task_id)


def _task_directories(root: Path) -> Iterator[Path]:
    """Visit only valid type/Task directories, never following symlinks."""
    for kind in KINDS:
        parent = root / kind
        try:
            if not stat.S_ISDIR(parent.lstat().st_mode):
                continue
            children = os.scandir(parent)
        except FileNotFoundError:
            continue
        with children:
            for child in children:
                if not child.is_dir(follow_symlinks=False):
                    continue
                try:
                    parse_task_directory(f"{kind}/{child.name}")
                except ValueError:
                    continue
                yield Path(child.path)


def scan_entries(root: Path) -> dict[str, TaskMetadata]:
    """Read all valid Task records without descending into their artifacts."""
    return {
        directory.name: entry
        for directory in _task_directories(root)
        if (entry := read_task_metadata(directory, directory.name)) is not None
    }


def scan_metadata(
    root: Path,
    previous: dict[str, TaskMetadata],
    versions: dict[str, FileVersion],
) -> tuple[dict[str, TaskMetadata], dict[str, FileVersion]]:
    """Reuse unchanged records; propagate I/O errors before replacing the index."""
    entries = {}
    current = {}
    for directory in _task_directories(root):
        task_id = directory.name
        try:
            info = (directory / METADATA_FILE).lstat()
        except FileNotFoundError:
            continue
        if not stat.S_ISREG(info.st_mode):
            continue
        version = (info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        entry = previous.get(task_id)
        if entry is None or versions.get(task_id) != version:
            entry = read_task_metadata(directory, task_id, strict_io=True)
            if entry is None:
                # Retry incomplete/invalid publications without dropping the last valid record.
                if task_id in previous:
                    entries[task_id] = previous[task_id]
                    if task_id in versions:
                        current[task_id] = versions[task_id]
                continue
        entries[task_id] = entry
        current[task_id] = version
    return entries, current


def load_task_metadata(directory: Path, task_id: str) -> TaskMetadata:
    """Require a valid record before any existing Task files may be replaced."""
    path = directory / METADATA_FILE
    if not is_task_directory(directory):
        raise ValueError(f"Invalid Task directory: {directory}")
    try:
        regular = stat.S_ISREG(path.lstat().st_mode)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Task metadata is missing: {path}; existing Task files were not overwritten") from exc
    if not regular:
        raise ValueError(f"Task metadata must be a regular file: {path}; existing Task files were not overwritten")
    try:
        metadata = TaskMetadata.model_validate_json(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ValueError(
            f"Invalid Task metadata: {path}; the format is corrupt or incompatible. "
            "Inspect or migrate the record before retrying; existing Task files were not overwritten"
        ) from exc
    if metadata.task_id != task_id or metadata.task_type != task_type_from_id(task_id):
        raise ValueError(
            f"Task metadata identity differs from its directory: {path}; existing files were not overwritten"
        )
    return metadata


def read_task_metadata(directory: Path, task_id: str, *, strict_io: bool = False) -> TaskMetadata | None:
    """Observe a matching record, tolerating missing or invalid publications."""
    try:
        return load_task_metadata(directory, task_id)
    except FileNotFoundError:
        return None
    except OSError:
        if strict_io:
            raise
        return None
    except ValueError:
        return None


def write_task_metadata(directory: Path, metadata: TaskMetadata) -> None:
    """Atomically replace the complete record; non-finite output values become null."""
    atomic_write_json(directory / METADATA_FILE, _finite(metadata.model_dump(mode="json")))


def _finite(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: _finite(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_finite(item) for item in value]
    return value


def task_id_from_path(root: Path, raw_path: str) -> str | None:
    """Return the task ID owning any changed path below its directory."""
    try:
        parts = Path(raw_path).relative_to(root).parts
    except ValueError:
        return None
    if len(parts) < 2:
        return None
    try:
        parse_task_directory(f"{parts[0]}/{parts[1]}")
    except ValueError:
        return None
    return parts[1]


def resolve_relative_path(root: Path, relative_path: str) -> Path:
    """Resolve a non-root owned path without traversing symlinks."""
    if not isinstance(relative_path, str) or not relative_path.strip():
        raise ValueError("Task path must be a non-empty relative path")
    candidate = Path(relative_path)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("Task path must stay inside the workspace")
    root = root.resolve()
    current = root
    for part in candidate.parts:
        current /= part
        if current.is_symlink():
            raise ValueError("Task paths cannot traverse symlinks")
    target = current.resolve()
    if target == root or not target.is_relative_to(root):
        raise ValueError("Task path must stay inside the workspace")
    return target
