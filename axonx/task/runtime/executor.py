"""Execute synchronous Tasks through one lifecycle, including child Tasks."""

# Internal wiring intentionally uses private runtime hooks.
# pylint: disable=protected-access

from __future__ import annotations

import fcntl
import inspect
import os
from collections.abc import Callable
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta
from functools import partial
from time import perf_counter
from typing import TYPE_CHECKING, Literal

from loguru import logger

from ...utils.logging import get_log_path, log_file
from ..core.base import ChildTaskError
from ..models.artifacts import PROTOCOL_VERSION
from ..models.identity import TaskState, validate_registration_name
from ..models.lifecycle import ChildTaskRecord, ChildTaskResult, TaskMetadata
from ..storage.workspace import LOG_FILE
from .lifecycle import finish_task, prepare_task_directory
from .process import machine_id, process_started_at
from .progress import TaskProgress
from .settings import normalize_execution_target

if TYPE_CHECKING:
    from ..core.base import BaseTask

_LOG_TASKS: ContextVar[tuple[str, ...]] = ContextVar("axonx_log_tasks", default=())


@contextmanager
def _task_log_scope(task: BaseTask, started_at: datetime):
    """Capture this Task and nested children while excluding sibling executions."""
    scope = f"{task.task_id}:{started_at.isoformat()}"
    tasks = (*_LOG_TASKS.get(), scope)
    token = _LOG_TASKS.set(tasks)
    try:
        with ExitStack() as stack:
            path = None
            if get_log_path() is not None:
                path = task.task_dir / LOG_FILE
                handle = stack.enter_context(path.open("ab"))
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                stack.enter_context(log_file(path, predicate=lambda record: scope in record["extra"].get("tasks", ())))
            with logger.contextualize(tasks=tasks):
                yield path
    finally:
        _LOG_TASKS.reset(token)


class TaskExecutor:
    """Own a Task's full lifecycle; keep execution state local to each run."""

    def __init__(self, *, resolve_task: Callable[[str], type[BaseTask]] | None = None) -> None:
        self.resolve_task = resolve_task

    @staticmethod
    def _close_after_error(task: BaseTask) -> None:
        try:
            task.close()
        except Exception:
            task.logger.exception("Task resource cleanup failed")

    def _execute_child(
        self,
        parent: BaseTask,
        reg_name: str,
        *,
        node_name: str | None,
        on_error: Literal["stop", "continue"],
        task_name: str | None,
        inputs: dict,
    ) -> ChildTaskResult:
        """Record and execute one direct child, including failures before startup."""
        validate_registration_name(reg_name)
        node_name = validate_registration_name(
            node_name or (f"{task_name}-{reg_name}" if task_name is not None else reg_name)
        )
        if on_error not in {"stop", "continue"}:
            raise ValueError("on_error must be 'stop' or 'continue'")
        previous = [child for child in parent.metadata.children if child.node_name == node_name]
        if any(child.reg_name != reg_name for child in previous):
            raise ValueError(f"Node {node_name!r} already refers to another Task")
        record = ChildTaskRecord(node_name=node_name, attempt=len(previous) + 1, reg_name=reg_name)
        parent.metadata.children.append(record)
        parent.persist_metadata()
        output = None
        error = None

        def observe(started_at):
            record.started_at = started_at
            parent.persist_metadata()

        try:
            if self.resolve_task is None:
                raise RuntimeError("Child Tasks require a task resolver")
            child = self.resolve_task(reg_name)(
                {"task_name": task_name if task_name is not None else parent.input_params.task_name, **inputs},
                workspace_path=parent.workspace_path,
                reg_name=reg_name,
                timezone=parent.context.timezone,
                parent_task_id=parent.task_id,
                execution_target=parent.context.execution_target,
                clock=parent.clock,
            )
            record.child_task_id = child.task_id
            try:
                parent.persist_metadata()
            except BaseException:
                self._close_after_error(child)
                raise
            status = self.execute(child, on_started=observe)
            record.state, record.exit_code, record.error = status.state, status.exit_code, status.error
            output = child.output_params
        except BaseException as exc:
            record.state = TaskState.FAILED
            record.exit_code = 1
            record.error = f"{type(exc).__name__}: {exc}"
            if not isinstance(exc, Exception):
                raise
            error = exc
        finally:
            parent.persist_metadata()
        result = ChildTaskResult(record.model_copy(deep=True), output)
        if not result.success and on_error == "stop":
            raise ChildTaskError(result) from error
        return result

    @staticmethod
    def _execute_step(task: BaseTask, progress: TaskProgress, step: Callable[[], None]) -> None:
        name = getattr(step, "__name__", type(step).__name__)
        if inspect.iscoroutinefunction(step):
            raise TypeError(f"Task step {name!r} must be synchronous")
        started = perf_counter()
        try:
            with progress.step(name):
                task.logger.info(f"Task step started step={name}")
                result = step()
                if inspect.isawaitable(result):
                    if inspect.iscoroutine(result):
                        result.close()
                    raise TypeError(f"Task step {name!r} returned an awaitable")
        except BaseException as exc:
            task.logger.error(
                f"Task step failed step={name} elapsed_seconds={perf_counter() - started:.3f} "
                f"error={type(exc).__name__}: {exc}",
            )
            raise
        task.logger.info(f"Task step completed step={name} elapsed_seconds={perf_counter() - started:.3f}")

    def execute(self, task: BaseTask, *, on_started: Callable[[datetime], None] | None = None) -> TaskMetadata:
        """Close resources even on startup rejection; publish only this run's record."""
        started = perf_counter()
        status = None
        with ExitStack() as stack:
            try:
                try:
                    execution_target = normalize_execution_target(task.context.execution_target)
                    previous_start = stack.enter_context(prepare_task_directory(task))
                    started_at = datetime.now(UTC)
                    if previous_start is not None:
                        started_at = max(started_at, previous_start + timedelta(microseconds=1))
                    log_path = stack.enter_context(_task_log_scope(task, started_at))
                    status = TaskMetadata(
                        version=PROTOCOL_VERSION,
                        task_id=task.task_id,
                        task_type=task.task_type,
                        reg_name=task.reg_name,
                        parent_task_id=task.context.parent_task_id,
                        report_kind=task.report_kind,
                        input_params=task.input_params.model_dump(mode="json"),
                        pid=os.getpid(),
                        machine_id=machine_id(),
                        execution_target=execution_target,
                        workspace_dir=str(task.workspace_path),
                        process_started_at=process_started_at(),
                        created_at=task.created_at,
                        started_at=started_at,
                        log_path=LOG_FILE if log_path else "",
                    )
                    progress = TaskProgress(task.task_dir, status, previous_started_at=previous_start)
                    task._metadata = status
                    task._persist_metadata = progress.publish
                    task._progress = progress.report
                    task._execute_child = partial(self._execute_child, task)
                    task.logger.info(f"Task started task_id={task.task_id} task_type={task.task_type.value}")
                    progress.publish()
                    if on_started is not None:
                        on_started(started_at)
                    for step in task.build_task_steps():
                        self._execute_step(task, progress, step)
                except BaseException:
                    self._close_after_error(task)
                    raise
                else:
                    task.close()
                task._output_params = task._build_output()
                output = task.output
                exit_code = task.exit_code(output)
                status.output_params = output
                finish_task(
                    status, exit_code=exit_code, error=f"Task exited with code {exit_code}" if exit_code else ""
                )
                task.logger.info(
                    f"Task completed task_id={task.task_id} exit_code={exit_code} "
                    f"elapsed_seconds={perf_counter() - started:.3f}",
                )
                progress.publish()
                return status
            except BaseException as exc:
                # Startup rejection must never write into another execution's directory.
                if status is None:
                    raise
                try:
                    task.on_failure(exc)
                except Exception:
                    task.logger.exception("Task failure callback failed")
                finish_task(status, exit_code=1, error=f"{type(exc).__name__}: {exc}")
                task.logger.exception(
                    f"Task failed task_id={task.task_id} elapsed_seconds={perf_counter() - started:.3f} "
                    f"error={type(exc).__name__}",
                )
                progress.publish()
                raise
            finally:
                task._progress = None
                task._persist_metadata = None
                task._execute_child = None
