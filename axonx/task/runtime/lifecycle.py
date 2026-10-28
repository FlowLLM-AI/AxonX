"""Prepare Task directories, settle lifecycle records and stop local executions."""

from __future__ import annotations

import math
import shlex
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import TYPE_CHECKING

import psutil

from ...utils.logging import get_logger
from ..models.identity import TaskState, task_type_from_id
from ..models.lifecycle import TaskMetadata
from ..storage.logs import TaskJournal
from ..storage.workspace import (
    EVENTS_FILE,
    load_task_metadata,
    read_task_metadata,
    reset_task_directory,
    scan_entries,
    task_path,
    write_task_metadata,
)
from .process import machine_id, process_instance, signal_process, wait_processes

if TYPE_CHECKING:
    from ..core.base import BaseTask


def prepare_task_directory(task: BaseTask) -> datetime | None:
    """Check replacement eligibility before clearing files; retain persistent data."""
    if task_type_from_id(task.task_id) != task.task_type:
        raise ValueError(f"Task type does not match its ID: {task.task_id}")
    if task.task_dir.parent.is_symlink():
        raise ValueError(f"Task type directory cannot be a symlink: {task.task_dir.parent}")
    if task.task_dir.is_symlink():
        raise ValueError(f"Task directory cannot be a symlink: {task.task_dir}")
    if not task.task_dir.exists():
        task.task_dir.mkdir(parents=True)
        return None

    previous = load_task_metadata(task.task_dir, task.task_id)
    if previous.replica is not None:
        raise ValueError("Display replicas are read-only; execute on the source service")
    try:
        previous = reconcile_record(task.task_dir, previous)
    except psutil.AccessDenied:
        raise FileExistsError(conflict_message(task.workspace_path, previous, process_verified=False)) from None
    if previous.state == TaskState.RUNNING:
        raise FileExistsError(conflict_message(task.workspace_path, previous))
    if task.is_generated_name:
        raise FileExistsError(f"Task directory already exists: {task.task_dir}")
    task.logger.info(
        f"Overwrite task_id={task.task_id} started_at={previous.started_at.isoformat()} state={previous.state.value}"
    )
    reset_task_directory(task.task_dir)
    return previous.started_at


def finish_task(metadata: TaskMetadata, *, exit_code: int, error: str = "") -> None:
    """Set a terminal outcome after resource cleanup or confirmed process exit."""
    metadata.state = TaskState.SUCCEEDED if exit_code == 0 else TaskState.FAILED
    metadata.exit_code = exit_code
    metadata.error = error
    metadata.finished_at = datetime.now(UTC)
    for step in metadata.steps:
        if step.state in {"pending", "waiting", "running"}:
            step.state = "failed" if exit_code else "skipped"
            step.error = error
            step.finished_at = step.updated_at = metadata.finished_at


def is_local_task(metadata: TaskMetadata) -> bool:
    return metadata.replica is None and metadata.machine_id == machine_id()


def reconcile_record(directory: Path, metadata: TaskMetadata) -> TaskMetadata:
    """Settle a confirmed dead local Task during startup or explicit termination."""
    if metadata.state != TaskState.RUNNING or not is_local_task(metadata):
        return metadata
    if process_instance(metadata.pid, metadata.process_started_at) is not None:
        return metadata
    now = datetime.now(UTC)
    reason = f"Execution process exited or PID was reused: pid={metadata.pid}; detected_at={now.isoformat()}"
    metadata = metadata.model_copy(deep=True)
    # Detection time; the actual exit time is unknown.
    finish_task(metadata, exit_code=1, error=reason)
    for child in metadata.children:
        if child.state != TaskState.RUNNING:
            continue
        child.state, child.exit_code, child.error = TaskState.FAILED, 1, reason
    TaskJournal(directory / EVENTS_FILE).append_snapshots(metadata.steps)
    write_task_metadata(directory, metadata)
    get_logger("task").warning(
        f"Reconciled stale Task task_id={metadata.task_id} machine_id={metadata.machine_id} "
        f"started_at={metadata.started_at.isoformat()} state=running->failed: {reason}"
    )
    return metadata


def reconcile_task(directory: Path, started_at: datetime) -> TaskMetadata | None:
    """Re-read the expected execution before settling an exited local process."""
    current = read_task_metadata(directory, directory.name, strict_io=True)
    if current is not None and current.started_at == started_at:
        try:
            return reconcile_record(directory, current)
        except psutil.AccessDenied:
            return current
    return current


def execution_owner(root: Path, metadata: TaskMetadata) -> TaskMetadata:
    """Resolve a child Task's shared process to its root execution record."""
    entries = scan_entries(root) if metadata.parent_task_id else {}
    seen = set()
    while metadata.parent_task_id and metadata.task_id not in seen:
        seen.add(metadata.task_id)
        parent = entries.get(metadata.parent_task_id)
        if (
            parent is None
            or parent.state != TaskState.RUNNING
            or parent.started_at > metadata.started_at
            or (parent.machine_id, parent.pid, parent.process_started_at)
            != (metadata.machine_id, metadata.pid, metadata.process_started_at)
        ):
            break
        metadata = parent
    return metadata


def conflict_message(root: Path, metadata: TaskMetadata, *, process_verified: bool = True) -> str:
    owner = execution_owner(root, metadata)
    arguments = ["axonx", "kill", "--task-id", owner.task_id]
    local = is_local_task(owner)
    if local:
        arguments.extend(["--workspace-dir", str(root)])
        state = (
            "Task is running"
            if process_verified
            else "Task is recorded as running; cannot verify the local process (access denied)"
        )
    else:
        arguments.extend(["--target", owner.execution_target or "<HOST:PORT>"])
        if owner.workspace_dir is not None:
            arguments.extend(["--workspace-dir", owner.workspace_dir])
        state = "Task is recorded as running on another machine; its process cannot be verified or repaired here"
    command = shlex.join(arguments)
    return (
        f"{state}: task_id={metadata.task_id} started_at={metadata.started_at.isoformat()} "
        f"machine_id={metadata.machine_id} pid={metadata.pid} "
        f"process_started_at={metadata.process_started_at.isoformat()}. "
        f"Wait for completion or explicitly stop the execution before rerunning: {command}. "
        f"This stops the execution process and its child Tasks; "
        f"observed_workspace={root}; execution_workspace={owner.workspace_dir or 'unknown'}"
    )


def kill_task(root: Path, task_id: str, *, timeout: float = 5, force: bool = False) -> TaskMetadata:
    """Stop a local Task, checking its execution identity before each signal phase."""
    if not math.isfinite(timeout) or timeout <= 0 or not isinstance(force, bool):
        raise ValueError("timeout must be finite and positive; force must be a boolean")
    directory = task_path(root, task_id)
    metadata = read_task_metadata(directory, task_id, strict_io=True)
    if metadata is None:
        raise ValueError(f"Task not found: {task_id}")
    if not is_local_task(metadata):
        raise ValueError("Only an original Task on this machine can be terminated")
    if metadata.state.is_terminal:
        return metadata
    owner = execution_owner(root, metadata)
    owner_directory = task_path(root, owner.task_id)

    def read_current():
        current = read_task_metadata(owner_directory, owner.task_id, strict_io=True)
        if current is None or current.started_at != owner.started_at:
            raise ValueError("Task restarted before termination")
        if not is_local_task(current):
            raise ValueError("Only an original Task on this machine can be terminated")
        return current

    deadline = monotonic() + timeout
    current = read_current()
    if current.state.is_terminal:
        return current
    process = process_instance(current.pid, current.process_started_at)
    try:
        children = process.children(recursive=True) if process is not None else []
    except psutil.NoSuchProcess:
        children = []
    for child in children:
        signal_process(child, force=force)
    # Keep the root alive until descendants exit, so a timeout remains retryable.
    wait_processes(children, max(0.001, deadline - monotonic()))
    current = read_current()
    if current.state.is_terminal:
        return current
    process = process_instance(current.pid, current.process_started_at)
    if process is not None:
        signal_process(process, force=force)
    wait_processes([process] if process is not None else [], max(0.001, deadline - monotonic()))
    identity = (current.machine_id, current.pid, current.process_started_at)
    for item in scan_entries(root).values():
        if item.state == TaskState.RUNNING and (item.machine_id, item.pid, item.process_started_at) == identity:
            reconcile_task(task_path(root, item.task_id), item.started_at)
    result = read_task_metadata(owner_directory, owner.task_id, strict_io=True)
    if result is None or result.started_at != owner.started_at:
        raise ValueError("Task restarted after termination; the replacement was left unchanged")
    return result
