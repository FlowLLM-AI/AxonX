"""Synchronous execution of Task steps."""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

from ..schema import TaskStatus
from .task_status_manager import StatusCallback, TaskStatusManager

if TYPE_CHECKING:
    from .base_task import BaseTask


def _step_name(step) -> str:
    name = getattr(step, "__name__", None)
    return name if isinstance(name, str) else type(step).__name__


class TaskRunner:
    """Run synchronous Task steps on the calling thread."""

    def __init__(self, emit: StatusCallback | None = None) -> None:
        self.emit = emit

    def run(self, task: BaseTask) -> TaskStatus:
        """Execute one Task and return its final status."""
        manager = TaskStatusManager(task.prepare_status(), self.emit)
        task._bind_status_manager(manager)
        manager.report()
        try:
            manager.start()
            for step in task.build_task_steps():
                self._run_step(step, manager)
            output = task.output
            manager.succeed(output, task.exit_code(output))
            return manager.status
        except BaseException as exc:
            manager.fail(exc)
            raise
        finally:
            task._bind_status_manager(None)

    @staticmethod
    def _run_step(step, manager: TaskStatusManager) -> None:
        if inspect.iscoroutinefunction(step):
            raise TypeError(f"Task step {_step_name(step)!r} must be synchronous")
        manager.begin_step(_step_name(step))
        try:
            result = step()
            if inspect.isawaitable(result):
                if inspect.iscoroutine(result):
                    result.close()
                raise TypeError(f"Task step {_step_name(step)!r} returned an awaitable")
        except BaseException:
            manager.finish_step(False)
            raise
        manager.finish_step(True)
