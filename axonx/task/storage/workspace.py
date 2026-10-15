"""One atomic lifecycle record and one append-only event journal per Task directory."""

from __future__ import annotations

import math
import shutil
import stat
from pathlib import Path, PurePosixPath
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ...constants import AXONX_DEFAULT_ENCODING
from ...enums import TaskState, TaskType
from ...utils.fs import atomic_write_json
from ..core.identity import task_type_from_id
from ..protocol import Protocol
from ..status import TaskStatus
from .replica import DisplayReplica
from ...progress import TaskStepStatus

#: One workspace directory per task category holds that category's task directories.
KINDS = tuple(kind.value for kind in TaskType)

PERSISTENT_DIR = "persistent"
METADATA_FILE = "metadata.json"
#: The append-only log a worker writes its status transitions to, so a manager in
#: another process can follow a running task event by event.
EVENTS_FILE = "events.jsonl"


class ChildTaskRecord(BaseModel):
    """Snapshot of one child invocation; invalid inputs may have no Task ID."""

    model_config = ConfigDict(extra="forbid")
    node_name: str
    attempt: int = Field(ge=1)
    task: str
    task_id: str | None = None
    run_id: str
    state: TaskState = TaskState.QUEUED
    exit_code: int = Field(default=0, ge=0, le=255)
    error: str = ""


class TaskMetadata(Protocol, TaskStatus):
    """The complete current lifecycle record, from queued to terminal."""

    model_config = ConfigDict(extra="forbid")
    input_params: dict[str, Any] = Field(default_factory=dict)
    output_params: dict[str, Any] = Field(default_factory=dict)
    children: list[ChildTaskRecord] = Field(default_factory=list)
    steps: list[TaskStepStatus] = Field(default_factory=list)
    replica: DisplayReplica | None = None


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


def kind_directories(root: Path) -> tuple[Path, ...]:
    """Return the per-kind task directories under one workspace root."""
    return tuple(root / kind for kind in KINDS)


def ensure_kind_directories(root: Path) -> tuple[Path, ...]:
    """Return the per-kind task directories, creating any that are missing.

    A watcher requires its targets to exist, and a kind directory that is a
    symlink would take the watcher outside the workspace.
    """
    directories = kind_directories(root)
    for directory in directories:
        if directory.is_symlink():
            raise ValueError(f"Task directory cannot be a symlink: {directory}")
        directory.mkdir(parents=True, exist_ok=True)
    return directories


def is_task_directory(directory: Path, *, strict_io: bool = False) -> bool:
    """Whether a path is a task directory this process may read or write.

    A directory reached through a symlink is refused twice over: a write through one
    would land outside the workspace, and it would recreate a directory that a
    concurrent delete had just removed. Strict checks propagate I/O errors other
    than missing directories so callers can retry instead of treating them as gone.
    """
    if strict_io:
        try:
            return all(stat.S_ISDIR(parent.lstat().st_mode) for parent in (directory.parent, directory))
        except FileNotFoundError:
            return False
    return not directory.is_symlink() and not directory.parent.is_symlink() and directory.is_dir()


def reset_task_directory(directory: Path) -> None:
    """Clear run-owned files while retaining the Task's persistent data."""
    if not is_task_directory(directory, strict_io=True):
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


def scan_entries(root: Path) -> dict[str, TaskMetadata]:
    """Read every task directory below a workspace root, keyed by task ID."""
    entries: dict[str, TaskMetadata] = {}
    for parent in kind_directories(root):
        if parent.is_symlink() or not parent.is_dir():
            continue
        try:
            children = list(parent.iterdir())
        except FileNotFoundError:
            # The kind directory went away between the check and the read, so it
            # holds no tasks.
            continue
        for directory in children:
            if not is_task_directory(directory):
                continue
            try:
                parse_task_directory(f"{parent.name}/{directory.name}")
            except ValueError:
                continue
            if (entry := read_task_metadata(directory, directory.name)) is not None:
                entries[directory.name] = entry
    return entries


def read_task_metadata(directory: Path, task_id: str, *, strict_io: bool = False) -> TaskMetadata | None:
    """Read a matching regular record; strict reads propagate transient I/O failures."""
    path = directory / METADATA_FILE
    try:
        if not is_task_directory(directory, strict_io=strict_io) or not stat.S_ISREG(path.lstat().st_mode):
            return None
        metadata = TaskMetadata.model_validate_json(path.read_text(encoding=AXONX_DEFAULT_ENCODING))
    except FileNotFoundError:
        return None
    except OSError:
        if strict_io:
            raise
        return None
    except (UnicodeError, ValueError):
        return None
    return metadata if metadata.task_id == task_id and metadata.task_type == task_type_from_id(task_id) else None


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


def task_record_id_from_path(root: Path, raw_path: str) -> str | None:
    """Return the task ID when a change can alter its indexed record."""
    try:
        parts = Path(raw_path).relative_to(root).parts
    except ValueError:
        return None
    if len(parts) == 3:
        if parts[2] != METADATA_FILE:
            return None
    elif len(parts) != 2:
        return None
    return task_id_from_path(root, raw_path)
