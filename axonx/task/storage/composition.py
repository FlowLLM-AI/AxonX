"""Composition records and settlement after an owning worker stops."""

from __future__ import annotations

import stat
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ...enums import TaskState
from ...utils.fs import atomic_write_json
from .workspace import TaskStatus, is_task_directory, read_status, task_path

COMPOSITION_FILE = "composition.json"


class ChildTaskRecord(BaseModel):
    """One attempted child invocation; construction failures may have no Task ID."""

    model_config = ConfigDict(extra="forbid")
    node_name: str
    attempt: int = Field(ge=1)
    task: str
    task_id: str | None = None
    run_id: str
    state: TaskState = TaskState.QUEUED
    exit_code: int = Field(default=0, ge=0, le=255)
    error: str = ""


class TaskComposition(BaseModel):
    """Containment is separate from the child's declared data lineage."""

    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    task_id: str
    run_id: str
    children: list[ChildTaskRecord] = Field(default_factory=list)


def write_composition(directory: Path, composition: TaskComposition) -> None:
    atomic_write_json(directory / COMPOSITION_FILE, composition.model_dump(mode="json"))


def read_composition(directory: Path, task_id: str, run_id: str) -> TaskComposition | None:
    """Read a regular record for this parent run; propagate I/O failures for retry."""
    path = directory / COMPOSITION_FILE
    try:
        if not is_task_directory(directory, strict_io=True) or not stat.S_ISREG(path.lstat().st_mode):
            return None
        composition = TaskComposition.model_validate_json(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, IsADirectoryError, NotADirectoryError):
        return None
    except (UnicodeError, ValueError):
        return None
    if (composition.task_id, composition.run_id) != (task_id, run_id):
        return None
    return composition


def settle_composition(
    workspace: Path,
    parent: TaskStatus,
    state: TaskState,
    code: int,
    error: str,
) -> list[TaskStatus]:
    """Return status updates for exact child runs after the shared worker stops.

    The manager persists/indexes the returned updates. Run identity and shared
    PID are both checked; stale records never settle replacement or foreign runs.
    """
    updates: list[TaskStatus] = []
    visited: set[tuple[str, str]] = set()

    def visit(owner: TaskStatus) -> None:
        identity = (owner.task_id, owner.run_id)
        if identity in visited:
            return
        visited.add(identity)
        directory = task_path(workspace, owner.task_id)
        composition = read_composition(directory, *identity)
        if composition is None:
            return
        changed = False
        for child in composition.children:
            if child.task_id is None:
                if not child.state.is_terminal:
                    child.state, child.exit_code, child.error = state, code, error
                    changed = True
                continue
            try:
                status = read_status(task_path(workspace, child.task_id), child.task_id, strict_io=True)
            except ValueError:
                continue
            if status is None or status.run_id != child.run_id:
                if not child.state.is_terminal:
                    child.state, child.exit_code, child.error = state, code, error
                    changed = True
                continue
            if owner.pid is None or status.pid != owner.pid:
                continue
            visit(status)
            if not status.state.is_terminal:
                status = status.model_copy(
                    update={"state": state, "exit_code": code, "error": error, "finished_at": datetime.now(UTC)}
                )
                updates.append(status)
            if (child.state, child.exit_code, child.error) != (status.state, status.exit_code, status.error):
                child.state, child.exit_code, child.error = status.state, status.exit_code, status.error
                changed = True
        if changed:
            write_composition(directory, composition)

    current = read_status(task_path(workspace, parent.task_id), parent.task_id, strict_io=True)
    if current is not None and current.run_id == parent.run_id:
        visit(current)
    return updates
