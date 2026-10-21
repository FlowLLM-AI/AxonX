"""Settle exact child Runs after their owning worker has stopped."""

from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path

from ...enums import TaskState
from ...progress import settle_steps
from ..schemas.lifecycle import TaskMetadata, same_worker
from ..storage.locking import workspace_lock
from ..storage.workspace import read_task_metadata, task_path


def settle_children(
    workspace: Path,
    parent: TaskMetadata,
    state: TaskState,
    code: int,
    error: str,
    *,
    recovery_locks: ExitStack | None = None,
) -> list[TaskMetadata]:
    """Update the parent's child snapshots and return changed child records.

    The manager owns the parent record and persists all updates after worker exit.
    Run ID and PID checks protect replacement and independently owned executions.
    Recovery can additionally require execution locks before changing each child.
    """
    updates: list[TaskMetadata] = []
    visited: set[tuple[str, str]] = set()

    def visit(owner: TaskMetadata) -> bool:
        identity = (owner.task_id, owner.run_id)
        if identity in visited:
            return False
        visited.add(identity)
        changed = False
        for child in owner.children:
            status = None
            if child.task_id is not None:
                status = read_task_metadata(task_path(workspace, child.task_id), child.task_id, strict_io=True)
            if status is None or status.run_id != child.run_id:
                if not child.state.is_terminal:
                    child.state, child.exit_code, child.error = state, code, error
                    changed = True
                continue
            if status.replica is not None or not same_worker(owner, status):
                continue
            if recovery_locks is not None and (status.task_id, status.run_id) not in visited:
                try:
                    recovery_locks.enter_context(workspace_lock(workspace, status.task_id))
                except BlockingIOError:
                    continue
            nested_changed = visit(status)
            if not status.state.is_terminal:
                status.state, status.exit_code, status.error = state, code, error
                status.finished_at = datetime.now(UTC)
                settle_steps(status.steps, failed=True, error=error, now=status.finished_at)
                nested_changed = True
            if nested_changed:
                updates.append(status)
            if (child.state, child.exit_code, child.error) != (
                status.state,
                status.exit_code,
                status.error,
            ):
                child.state, child.exit_code, child.error = (
                    status.state,
                    status.exit_code,
                    status.error,
                )
                changed = True
        return changed

    visit(parent)
    return updates
