"""Pure state transitions for local Task status snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import signal

from ....enums import TaskState
from ....schema import TaskStatus


@dataclass(frozen=True)
class WorkerExit:
    """Describe one unexpected worker exit."""

    pid: int
    return_code: int
    stderr_tail: str
    occurred_at: datetime


class TaskStateReconciler:
    """Resolve restart, cancellation, deletion, and worker-exit races."""

    def __init__(self) -> None:
        self._pending_exits: dict[int, tuple[int, str, datetime]] = {}
        self._deleted_task_ids: set[str] = set()

    @staticmethod
    def restore(status: TaskStatus) -> None:
        """Fail an unfinished status whose owning manager has restarted."""
        if status.state.is_terminal:
            return
        status.state = TaskState.FAILED
        status.finished_at = datetime.now(UTC)
        status.exit_code = 1
        status.error = "Task ownership was lost when the task manager stopped"

    def accept(
        self,
        task_id: str,
        current: TaskStatus | None,
        incoming: TaskStatus,
    ) -> TaskStatus | None:
        """Return the accepted snapshot, or ``None`` when a late report loses."""
        if task_id in self._deleted_task_ids:
            return None
        if current is not None and current.state.is_terminal:
            if current.state == TaskState.CANCELLED or not incoming.state.is_terminal:
                return None

        snapshot = incoming.model_copy(deep=True)
        if snapshot.pid is not None and not snapshot.state.is_terminal:
            pending = self._pending_exits.pop(snapshot.pid, None)
            if pending is not None:
                snapshot.exit_code, snapshot.error, snapshot.finished_at = pending
                snapshot.state = TaskState.FAILED
        return snapshot

    def record_exit(self, statuses: dict[str, TaskStatus], worker_exit: WorkerExit) -> bool:
        """Apply an abnormal exit now or retain it for a later first report."""
        exit_code, error = self._exit_failure(worker_exit.return_code, worker_exit.stderr_tail)
        changed = False
        for status in statuses.values():
            if status.pid == worker_exit.pid and not status.state.is_terminal:
                status.state = TaskState.FAILED
                status.finished_at = worker_exit.occurred_at
                status.exit_code = exit_code
                status.error = error
                changed = True
        if not changed:
            self._pending_exits[worker_exit.pid] = (exit_code, error, worker_exit.occurred_at)
        return changed

    @staticmethod
    def cancel(status: TaskStatus) -> None:
        """Transition one running status to the cancelled terminal state."""
        status.state = TaskState.CANCELLED
        status.finished_at = datetime.now(UTC)
        status.exit_code = 130

    @staticmethod
    def cancel_pids(statuses: dict[str, TaskStatus], pids: set[int]) -> None:
        """Cancel non-terminal statuses belonging to stopped worker PIDs."""
        for status in statuses.values():
            if status.pid in pids and not status.state.is_terminal:
                TaskStateReconciler.cancel(status)

    def mark_deleted(self, task_id: str) -> None:
        """Prevent a delayed worker report from recreating a deleted status."""
        self._deleted_task_ids.add(task_id)

    @staticmethod
    def _exit_failure(return_code: int, stderr_tail: str) -> tuple[int, str]:
        if return_code < 0:
            signal_number = -return_code
            try:
                signal_name = signal.Signals(signal_number).name
            except ValueError:
                signal_name = f"signal {signal_number}"
            exit_code = min(255, 128 + signal_number)
            error = f"Worker terminated by signal {signal_name} ({signal_number})"
        else:
            exit_code = min(255, return_code)
            error = f"Worker exited unexpectedly with code {return_code}"
        if stderr_tail != "no stderr output":
            error = f"{error}: {stderr_tail[-2048:]}"
        return exit_code, error
