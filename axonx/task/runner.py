"""Run a task and persist its status in the task directory."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from datetime import UTC, datetime
from time import perf_counter
from typing import TYPE_CHECKING

from ..enums import TaskState
from ..schema import TaskStatus, TaskStepStatus
from ..utils.fs import atomic_write_json
from .base import task_type_from_id

if TYPE_CHECKING:
    from .base import BaseTask


class TaskRunner:
    def __init__(self, emit: Callable[[TaskStatus], None] | None = None) -> None:
        self.emit = emit
        self.task: BaseTask | None = None
        self.step: TaskStepStatus | None = None

    def _publish(self) -> None:
        task = self.task
        assert task is not None
        atomic_write_json(task.task_dir / "status.json", task.status.model_dump(mode="json"))
        if self.emit is not None:
            self.emit(task.status.model_copy(deep=True))

    def progress(self, percentage: float) -> None:
        step = self.step
        if step is None:
            raise RuntimeError("Progress can only be reported while a task step is running")
        if not 0 <= percentage <= 100:
            raise ValueError("percentage must be between 0 and 100")
        if step.percentage is not None and percentage < step.percentage:
            raise ValueError("percentage cannot move backwards")
        step.percentage = percentage
        self._publish()

    def _run_step(self, step: Callable[[], None]) -> None:
        task = self.task
        assert task is not None
        name = getattr(step, "__name__", type(step).__name__)
        if inspect.iscoroutinefunction(step):
            raise TypeError(f"Task step {name!r} must be synchronous")
        current = TaskStepStatus(name=name, started_at=datetime.now(UTC))
        self.step = current
        task.status.steps.append(current)
        self._publish()
        started = perf_counter()
        task.logger.info(f"Task step started step={name}")
        try:
            result = step()
            if inspect.isawaitable(result):
                if inspect.iscoroutine(result):
                    result.close()
                raise TypeError(f"Task step {name!r} returned an awaitable")
        except BaseException as exc:
            current.finished_at = datetime.now(UTC)
            self._publish()
            task.logger.error(
                f"Task step failed step={name} elapsed_seconds={perf_counter() - started:.3f} "
                f"error={type(exc).__name__}: {exc}",
            )
            raise
        current.percentage = 100
        current.finished_at = datetime.now(UTC)
        self._publish()
        self.step = None
        task.logger.info(f"Task step completed step={name} elapsed_seconds={perf_counter() - started:.3f}")

    def run(self, task: BaseTask) -> TaskStatus:
        if task_type_from_id(task.task_id) != task.task_type:
            raise ValueError(f"Task type does not match its ID: {task.task_id}")
        if task.task_dir.parent.is_symlink():
            raise ValueError(f"Task type directory cannot be a symlink: {task.task_dir.parent}")
        task.task_dir.mkdir(parents=True, exist_ok=False)
        self.task = task
        task._runner = self
        started = perf_counter()
        try:
            self._publish()
            task.logger.info(f"Task started task_id={task.task_id} task_type={task.task_type.value}")
            task.status.state = TaskState.RUNNING
            task.status.started_at = datetime.now(UTC)
            self._publish()
            for step in task.build_task_steps():
                self._run_step(step)
            task.prepare_output()
            output = task.output
            exit_code = task.exit_code(output)
            task.status.exit_code = exit_code
            task.status.result = output
            task.status.state = TaskState.SUCCEEDED if exit_code == 0 else TaskState.FAILED
            task.status.error = "" if exit_code == 0 else f"Task exited with code {exit_code}"
            task.status.finished_at = datetime.now(UTC)
            self._publish()
            if exit_code == 0:
                task._write_metadata()
            task.logger.info(
                f"Task completed task_id={task.task_id} exit_code={exit_code} "
                f"elapsed_seconds={perf_counter() - started:.3f}",
            )
            return task.status
        except BaseException as exc:
            task.status.state = TaskState.FAILED
            task.status.exit_code = 1
            task.status.error = f"{type(exc).__name__}: {exc}"
            task.status.finished_at = datetime.now(UTC)
            self._publish()
            task.logger.exception(
                f"Task failed task_id={task.task_id} elapsed_seconds={perf_counter() - started:.3f} "
                f"error={type(exc).__name__}: {exc}",
            )
            raise
        finally:
            task._runner = None
            self.task = None
            self.step = None
