"""Synchronous execution of Task steps."""

from __future__ import annotations

import inspect
from time import perf_counter
from typing import TYPE_CHECKING

from ..schema import TaskStatus
from .status_manager import StatusCallback, TaskStatusManager

if TYPE_CHECKING:
    from .base import BaseTask


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
        task._bind_status_manager(manager)  # pylint: disable=protected-access
        manager.report()
        started = perf_counter()
        task.logger.info(
            f"Task started task_id={task.task_id} task_type={task.task_type.value}"
        )
        try:
            manager.start()
            for step in task.build_task_steps():
                self._run_step(step, manager, task.logger)
            output = task.output
            exit_code = task.exit_code(output)
            manager.succeed(output, exit_code)
            task.logger.info(
                f"Task completed task_id={task.task_id} exit_code={exit_code} "
                f"elapsed_seconds={perf_counter() - started:.3f}"
            )
            return manager.status
        except BaseException as exc:
            manager.fail(exc)
            task.logger.exception(
                f"Task failed task_id={task.task_id} "
                f"elapsed_seconds={perf_counter() - started:.3f} "
                f"error={type(exc).__name__}: {exc}"
            )
            raise
        finally:
            task._bind_status_manager(None)  # pylint: disable=protected-access

    @staticmethod
    def _run_step(step, manager: TaskStatusManager, logger) -> None:
        if inspect.iscoroutinefunction(step):
            raise TypeError(f"Task step {_step_name(step)!r} must be synchronous")
        name = _step_name(step)
        manager.begin_step(name)
        started = perf_counter()
        logger.info(f"Task step started step={name}")
        try:
            result = step()
            if inspect.isawaitable(result):
                if inspect.iscoroutine(result):
                    result.close()
                raise TypeError(f"Task step {name!r} returned an awaitable")
        except BaseException as exc:
            manager.finish_step(False)
            logger.error(
                f"Task step failed step={name} "
                f"elapsed_seconds={perf_counter() - started:.3f} "
                f"error={type(exc).__name__}: {exc}"
            )
            raise
        manager.finish_step(True)
        logger.info(
            f"Task step completed step={name} "
            f"elapsed_seconds={perf_counter() - started:.3f}"
        )
