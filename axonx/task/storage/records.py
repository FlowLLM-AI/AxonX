"""Local process reconciliation and short, cross-process metadata transactions."""

import math
import shlex
from contextlib import contextmanager
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from time import monotonic

import psutil

from ...common.fs.locking import file_lock
from ...common.process import (
    machine_id,
    process_instance,
    signal_process,
    wait_processes,
)
from ..task_enums import TaskState
from ..models.lifecycle import TaskMetadata
from ..progress import settle_steps
from .events import append_progress_snapshots
from .workspace import (
    KINDS,
    read_task_metadata,
    scan_entries,
    task_path,
    write_task_metadata,
)

RECORDS_DIRECTORY = ".task-records"


def validate_workspace_deletion(root: Path, targets: tuple[Path, ...]) -> None:
    """Protect metadata transactions and active Task files during workspace cleanup."""
    if any(target.relative_to(root).parts[0] == RECORDS_DIRECTORY for target in targets):
        raise ValueError("Task metadata transaction files cannot be deleted")
    entries = scan_entries(root) if any(target.relative_to(root).parts[0] in KINDS for target in targets) else {}
    for task_id, status in entries.items():
        directory = task_path(root, task_id)
        if any(target == directory or target in directory.parents or directory in target.parents for target in targets):
            if not status.state.is_terminal:
                raise ValueError(f"Cannot delete active Task files: {task_id}")


@contextmanager
def record_lock(directory: Path):
    """Serialize publication/reconciliation without locking a running Task."""
    locks = directory.parent.parent / RECORDS_DIRECTORY
    path = locks / f"{sha256(directory.name.encode()).hexdigest()}.lock"
    if locks.is_symlink() or path.is_symlink():
        raise ValueError("Task metadata locks cannot be symlinks")
    with file_lock(path, timeout=5):
        yield


def is_local_run(metadata: TaskMetadata) -> bool:
    return metadata.replica is None and metadata.machine_id == machine_id()


def reconcile_record(directory: Path, metadata: TaskMetadata) -> TaskMetadata:
    """Settle a confirmed dead local Run; caller holds its record lock."""
    if metadata.state != TaskState.RUNNING or not is_local_run(metadata):
        return metadata
    try:
        if process_instance(metadata.pid, metadata.process_started_at) is not None:
            return metadata
    except psutil.AccessDenied:
        return metadata
    now = datetime.now(UTC)
    reason = f"Execution process exited or PID was reused: pid={metadata.pid}; detected_at={now.isoformat()}"
    metadata = metadata.model_copy(deep=True)
    metadata.state = TaskState.FAILED
    metadata.exit_code = 1
    metadata.error = reason
    metadata.finished_at = now  # Detection time; the actual exit time is unknown.
    settle_steps(metadata.steps, failed=True, error=reason, now=now)
    for child in metadata.children:
        if child.state != TaskState.RUNNING:
            continue
        child.state, child.exit_code, child.error = TaskState.FAILED, 1, reason
    append_progress_snapshots(directory, metadata.steps)
    write_task_metadata(directory, metadata)
    return metadata


def reconcile_task(directory: Path, run_id: str) -> TaskMetadata | None:
    """Re-read under the lock so an observer can never settle a replacement Run."""
    with record_lock(directory):
        current = read_task_metadata(directory, directory.name, strict_io=True)
        if current is not None and current.run_id == run_id:
            return reconcile_record(directory, current)
        return current


def execution_owner(root: Path, metadata: TaskMetadata) -> TaskMetadata:
    """Resolve a composite's shared process to its root execution record."""
    entries = {item.run_id: item for item in scan_entries(root).values()} if metadata.parent_run_id else {}
    seen = set()
    while metadata.parent_run_id and metadata.run_id not in seen:
        seen.add(metadata.run_id)
        parent = entries.get(metadata.parent_run_id)
        if parent is None or (parent.machine_id, parent.pid, parent.process_started_at) != (
            metadata.machine_id,
            metadata.pid,
            metadata.process_started_at,
        ):
            break
        metadata = parent
    return metadata


def conflict_message(root: Path, metadata: TaskMetadata) -> str:
    owner = execution_owner(root, metadata)
    arguments = ["axonx", "kill", "--task-id", owner.task_id, "--run-id", owner.run_id]
    if is_local_run(owner):
        arguments.extend(["--workspace-dir", str(root)])
    command = shlex.join(arguments)
    location = (
        "on this machine"
        if owner.machine_id == machine_id()
        else "on the execution machine (or add --target HOST:PORT)"
    )
    return (
        f"Task is running: task_id={metadata.task_id} run_id={metadata.run_id} "
        f"machine_id={metadata.machine_id} pid={metadata.pid} "
        f"process_started_at={metadata.process_started_at.isoformat()}. "
        f"Wait for completion or run {location}: {command}. "
        f"This stops the execution process and its child Tasks; workspace={root}"
    )


def kill_task(root: Path, task_id: str, run_id: str, *, timeout: float = 5, force: bool = False) -> TaskMetadata:
    """Explicitly stop an exact local Run, then reconcile its persisted records."""
    if not math.isfinite(timeout) or timeout <= 0 or not isinstance(force, bool):
        raise ValueError("timeout must be finite and positive; force must be a boolean")
    directory = task_path(root, task_id)
    metadata = read_task_metadata(directory, task_id, strict_io=True)
    if metadata is None or metadata.run_id != run_id:
        raise ValueError("Task Run does not match the requested run_id")
    if not is_local_run(metadata):
        raise ValueError("Only an original Run on this machine can be terminated")
    owner = execution_owner(root, metadata)
    owner_directory = task_path(root, owner.task_id)

    def read_current():
        current = read_task_metadata(owner_directory, owner.task_id, strict_io=True)
        if current is None or current.run_id != owner.run_id:
            raise ValueError("Task Run changed before termination")
        if not is_local_run(current):
            raise ValueError("Only an original Run on this machine can be terminated")
        return current

    deadline = monotonic() + timeout
    with record_lock(owner_directory):
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
    with record_lock(owner_directory):
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
            reconcile_task(task_path(root, item.task_id), item.run_id)
    result = read_task_metadata(owner_directory, owner.task_id, strict_io=True)
    if result is None or result.run_id != owner.run_id:
        raise ValueError("Task Run changed after termination; the replacement was left unchanged")
    return result
