"""Pure synchronous state transitions for one Task execution."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable

from ..enumeration import TaskState
from ..schema import TaskStatus, TaskStepStatus

StatusCallback = Callable[[TaskStatus], None]


class TaskStatusManager:
    """Own Task status state without knowing how snapshots are transported."""

    def __init__(self, status: TaskStatus, emit: StatusCallback | None = None) -> None:
        self.status = status
        self._emit = emit or (lambda _status: None)
        self._active_step: TaskStepStatus | None = None

    def snapshot(self) -> TaskStatus:
        """Return an immutable-by-convention snapshot for observers."""
        return self.status.model_copy(deep=True)

    def report(self) -> None:
        """Publish the latest complete status snapshot."""
        self._emit(self.snapshot())

    def start(self) -> None:
        """Mark the Task as running."""
        self.status.state = TaskState.RUNNING
        self.status.started_at = datetime.now(UTC)
        self.report()

    def begin_step(self, name: str) -> None:
        """Append and activate the next Task step."""
        step = TaskStepStatus(name=name, started_at=datetime.now(UTC))
        self._active_step = step
        self.status.steps.append(step)
        self.report()

    def finish_step(self, completed: bool) -> None:
        """Finish the active step and optionally mark full progress."""
        step = self._step()
        if completed:
            step.percentage = 100
        step.finished_at = datetime.now(UTC)
        self.report()

    def progress(self, percentage: float) -> None:
        """Update progress for the active step."""
        if not 0 <= percentage <= 100:
            raise ValueError("percentage must be between 0 and 100")
        step = self._step()
        if step.percentage is not None and percentage < step.percentage:
            raise ValueError("percentage cannot move backwards")
        step.percentage = percentage
        self.report()

    def succeed(self, result: dict[str, Any], exit_code: int) -> None:
        """Store Task output and its successful or nonzero terminal state."""
        state = TaskState.SUCCEEDED if exit_code == 0 else TaskState.FAILED
        error = "" if exit_code == 0 else f"Task exited with code {exit_code}"
        self._finish(state, exit_code, result=result, error=error)

    def fail(self, exc: BaseException) -> None:
        """Store a failed terminal state."""
        self._finish(TaskState.FAILED, 1, error=f"{type(exc).__name__}: {exc}")

    def _step(self) -> TaskStepStatus:
        if self._active_step is None:
            raise RuntimeError("Progress can only be reported while a task step is running")
        return self._active_step

    def _finish(
        self,
        state: TaskState,
        exit_code: int,
        *,
        result: dict[str, Any] | None = None,
        error: str = "",
    ) -> None:
        self.status.state = state
        self.status.exit_code = exit_code
        self.status.result = result or {}
        self.status.error = error
        self.status.finished_at = datetime.now(UTC)
        self._active_step = None
        self.report()
