"""The on-disk layout of a Task workspace, and the records it holds.

A workspace root holds one directory per task category, one directory per task run
below it, and up to three files inside that one directory: ``status.json``, the
status a worker rewrites as it runs; ``metadata.json``, the record it writes once
the run succeeds; and ``events.jsonl``, the append-only status transitions a
follower replays. Everything that has to know that layout — the task runner, the
task manager and the sync component — reads it from here, so a change to it is one
edit rather than four.

These reads are the lenient side of the format. A task's files are written by
another process and may be half-written, hand-edited or foreign, so a file that
does not describe the task it sits under reads as absent rather than raising: a
workspace is what it is, not what it should be.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from pydantic import AliasChoices, BaseModel, Field

from ...constants import AXONX_DEFAULT_ENCODING
from ...enums import TaskState, TaskType
from ...utils.fs import atomic_write_json
from ..core.identity import task_type_from_id

#: One workspace directory per task category holds that category's task directories.
KINDS = tuple(kind.value for kind in TaskType)

STATUS_FILE = "status.json"
METADATA_FILE = "metadata.json"
#: The append-only log a worker writes its status transitions to, so a manager in
#: another process can follow a running task event by event.
EVENTS_FILE = "events.jsonl"
#: The two files whose changes can alter the task manager's indexed record.
RECORD_FILES = frozenset({STATUS_FILE, METADATA_FILE})


class TaskStepStatus(BaseModel):
    """Progress persisted for one Task step."""

    name: str = Field(min_length=1)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    percentage: float | None = Field(default=None, ge=0, le=100)


class TaskStatus(BaseModel):
    """Persisted mutable state of one Task run."""

    task_id: str
    run_id: str = Field(
        min_length=1,
        validation_alias=AliasChoices("run_id", "execution_id"),
    )
    task_type: TaskType
    task_name: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    state: TaskState = TaskState.QUEUED
    pid: int | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    steps: list[TaskStepStatus] = Field(default_factory=list)
    result: dict[str, Any] = Field(default_factory=dict)
    error: str = ""
    exit_code: int = Field(default=0, ge=0, le=255)
    log_path: str = ""


@dataclass(frozen=True)
class TaskRecord:
    """What a task directory declares about itself in ``metadata.json``."""

    task_id: str
    task_type: TaskType
    reg_name: str | None
    created_at: str | None
    source_tasks: tuple[str, ...]


@dataclass(frozen=True)
class TaskEntry:
    """One task directory, as read: the status it reported and the record it declares."""

    status: TaskStatus | None
    record: TaskRecord | None


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


def is_task_directory(directory: Path) -> bool:
    """Whether a path is a task directory this process may read or write.

    A directory reached through a symlink is refused twice over: a write through one
    would land outside the workspace, and it would recreate a directory that a
    concurrent delete had just removed.
    """
    return (
        not directory.is_symlink()
        and not directory.parent.is_symlink()
        and directory.is_dir()
    )


def read_entry(root: Path, task_id: str) -> TaskEntry | None:
    """Read one task directory, or None when it holds nothing to index."""
    directory = task_path(root, task_id)
    return _read(directory, task_id) if is_task_directory(directory) else None


def scan_entries(root: Path) -> dict[str, TaskEntry]:
    """Read every task directory below a workspace root, keyed by task ID."""
    entries: dict[str, TaskEntry] = {}
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
            if (entry := _read(directory, directory.name)) is not None:
                entries[directory.name] = entry
    return entries


def read_status(directory: Path, task_id: str) -> TaskStatus | None:
    """Read a task's persisted status, or None when it has none to read."""
    path = directory / STATUS_FILE
    if path.is_symlink():
        return None
    try:
        status = TaskStatus.model_validate_json(
            path.read_text(encoding=AXONX_DEFAULT_ENCODING)
        )
    except (OSError, UnicodeError, ValueError):
        return None
    return (
        status
        if status.task_id == task_id and status.task_type == task_type_from_id(task_id)
        else None
    )


def read_record(directory: Path, task_id: str) -> TaskRecord | None:
    """Read a task's record, or None when it declares nothing about this task."""
    path = directory / METADATA_FILE
    if path.is_symlink():
        return None
    try:
        value = json.loads(path.read_text(encoding=AXONX_DEFAULT_ENCODING))
    except (OSError, UnicodeError, ValueError):
        return None
    if not isinstance(value, dict):
        return None
    task_type = task_type_from_id(task_id)
    if value.get("task_id") != task_id or value.get("task_type") != task_type.value:
        return None
    return TaskRecord(
        task_id=task_id,
        task_type=task_type,
        reg_name=_text(value, "reg_name"),
        created_at=_text(value, "created_at"),
        source_tasks=_source_tasks(value.get("input_params"), task_id),
    )


def write_status(directory: Path, status: TaskStatus) -> None:
    """Persist one task status atomically, beside that task's other files."""
    atomic_write_json(directory / STATUS_FILE, status.model_dump(mode="json"))


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
        if parts[2] not in RECORD_FILES:
            return None
    elif len(parts) != 2:
        return None
    return task_id_from_path(root, raw_path)


def _read(directory: Path, task_id: str) -> TaskEntry | None:
    """Read both record files of one task directory, or None when neither holds anything."""
    entry = TaskEntry(read_status(directory, task_id), read_record(directory, task_id))
    return entry if entry.status is not None or entry.record is not None else None


def _text(value: dict, key: str) -> str | None:
    """Read one optional string field of a record document."""
    field = value.get(key)
    return field if isinstance(field, str) else None


def _source_tasks(input_params: Any, task_id: str) -> tuple[str, ...]:
    """Return the parent task IDs a record declares.

    A declared parent that does not name a task is dropped, and so is a task naming
    itself: the graph is drawn from records other processes wrote, so it survives a
    hand-edited or half-written one instead of failing on it.
    """
    params = input_params if isinstance(input_params, dict) else {}
    sources = params.get("source_tasks")
    parents: list[str] = []
    for source in sources if isinstance(sources, list) else []:
        try:
            task_type_from_id(source)
        except ValueError:
            continue
        if source != task_id and source not in parents:
            parents.append(source)
    return tuple(parents)
