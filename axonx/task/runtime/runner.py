"""Run a Task and persist each state transition."""

# Internal wiring intentionally uses private runtime hooks.
# pylint: disable=protected-access

from __future__ import annotations

import inspect
from collections.abc import Callable
from contextlib import ExitStack
from datetime import UTC, datetime
from time import perf_counter
from threading import RLock
from typing import TYPE_CHECKING

from ...components.job.events import ProgressEvent
from ...progress import settle_steps
from ...enums import TaskState
from ...utils.logging import task_log_scope
from ..schemas.protocol import PROTOCOL_VERSION
from ..core.identity import task_type_from_id
from ..storage.events import append_event, append_progress_snapshots
from ..storage.locking import workspace_lock
from ..storage.workspace import (
    EVENTS_FILE,
    TaskStepStatus,
    read_task_metadata,
    reset_task_directory,
    write_task_metadata,
)
from ..schemas.lifecycle import TaskMetadata

if TYPE_CHECKING:
    from ..core.task import BaseTask


class TaskRunner:
    def __init__(self, emit: Callable[[TaskMetadata], None] | None = None) -> None:
        self.emit = emit
        self.task: BaseTask | None = None
        self.status: TaskMetadata | None = None
        self.step: TaskStepStatus | None = None
        self._lock = RLock()
        self._progress_published: dict[tuple[str, str], float] = {}

    def _publish(self) -> None:
        with self._lock:
            self._publish_locked()

    def _publish_locked(self) -> None:
        task = self.task
        status = self.status
        assert task is not None and status is not None
        # Journal progress before publishing the matching status snapshot. A
        # follower that observes a terminal status has therefore already had a
        # chance to read every progress event leading to it.
        if self.emit is None and self.step is not None:
            append_event(task.task_dir / EVENTS_FILE, ProgressEvent.from_status(self.step))
        if status.state.is_terminal:
            settle_steps(
                status.steps,
                failed=status.state != TaskState.SUCCEEDED,
                error=status.error,
                now=datetime.now(UTC),
            )
            append_progress_snapshots(task.task_dir / EVENTS_FILE, status.steps)
        write_task_metadata(task.task_dir, status)
        if self.emit is not None:
            self.emit(status.model_copy(deep=True))

    def progress(self, percentage: float | None = None, *, name: str | None = None, **changes) -> None:
        with self._lock:
            step = self.step
            if step is None or self.status is None or self.task is None:
                raise RuntimeError("Progress can only be reported while a task step is running")
            if name is None:
                if changes or percentage is None or not 0 <= percentage <= 100:
                    raise ValueError("percentage must be between 0 and 100")
                if step.percentage is not None and percentage < step.percentage:
                    raise ValueError("percentage cannot move backwards")
                step.percentage = percentage
                self._publish_locked()
                return
            now = datetime.now(UTC)
            previous = next(
                (s for s in self.status.steps if s.parent == step.name and s.name == name),
                None,
            )
            values = previous.model_dump() if previous else {"name": name, "label": name, "parent": step.name}
            values.update(changes, name=name, parent=step.name, updated_at=now)
            if percentage is not None:
                values["percentage"] = percentage
            if values.get("state") == "running" and not values.get("started_at"):
                values["started_at"] = now
            terminal = values.get("state") in {"done", "failed", "missed", "skipped"}
            if terminal:
                values["finished_at"] = values.get("finished_at") or now
            updated = TaskStepStatus.model_validate(values)
            if previous is None:
                self.status.steps.append(updated)
            else:
                self.status.steps[self.status.steps.index(previous)] = updated
            transition = previous is None or (previous.state, previous.phase) != (
                updated.state,
                updated.phase,
            )
            identity = (step.name, name)
            if transition or terminal or perf_counter() - self._progress_published.get(identity, 0) >= 1:
                append_event(self.task.task_dir / EVENTS_FILE, ProgressEvent.from_status(updated))
                self._progress_published[identity] = perf_counter()
                self._publish_locked()

    def _run_step(self, step: Callable[[], None]) -> None:
        task = self.task
        status = self.status
        assert task is not None and status is not None
        name = getattr(step, "__name__", type(step).__name__)
        if inspect.iscoroutinefunction(step):
            raise TypeError(f"Task step {name!r} must be synchronous")
        current = TaskStepStatus(name=name, state="running", started_at=datetime.now(UTC))
        self.step = current
        status.steps.append(current)
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
            with self._lock:
                current.state = "failed"
                current.finished_at = datetime.now(UTC)
                self._publish_locked()
            task.logger.error(
                f"Task step failed step={name} elapsed_seconds={perf_counter() - started:.3f} "
                f"error={type(exc).__name__}: {exc}",
            )
            raise
        with self._lock:
            current.state = "done"
            current.percentage = 100
            current.finished_at = datetime.now(UTC)
            self._publish_locked()
        self.step = None
        task.logger.info(f"Task step completed step={name} elapsed_seconds={perf_counter() - started:.3f}")

    @staticmethod
    def _prepare_directory(task: BaseTask) -> None:
        if task_type_from_id(task.task_id) != task.task_type:
            raise ValueError(f"Task type does not match its ID: {task.task_id}")
        if task.task_dir.parent.is_symlink():
            raise ValueError(f"Task type directory cannot be a symlink: {task.task_dir.parent}")
        if task.task_dir.is_symlink():
            raise ValueError(f"Task directory cannot be a symlink: {task.task_dir}")
        if task.task_dir.exists():
            queued = read_task_metadata(task.task_dir, task.task_id)
            if queued is not None and queued.replica is not None:
                raise ValueError("Display replicas are read-only; execute on the source service")
            handed_over = (
                queued is not None and queued.state == TaskState.QUEUED and queued.run_id == task.context.run_id
            )
            replaceable = not task.is_generated_name and queued is not None and queued.state.is_terminal
            if replaceable:
                reset_task_directory(task.task_dir)
            elif not handed_over:
                raise FileExistsError(f"Task directory already exists: {task.task_dir}")
        else:
            task.task_dir.mkdir(parents=True)

    def run(self, task: BaseTask) -> TaskMetadata:
        """Own resource cleanup from entry, including rejected directory preparation."""
        with ExitStack() as stack:
            try:
                stack.enter_context(workspace_lock(task.workspace_path, task.task_id))
                log_path = stack.enter_context(task_log_scope(task.context.run_id))
            except BaseException:
                self._close_after_error(task)
                raise
            task.log_path = str(log_path or "")
            return self._run(task)

    @staticmethod
    def _close_after_error(task: BaseTask) -> None:
        try:
            task.close()
        except Exception:
            task.logger.exception("Task resource cleanup failed")

    def _run(self, task: BaseTask) -> TaskMetadata:
        self.task = task
        started = perf_counter()
        try:
            try:
                with workspace_lock(task.workspace_path, blocking=True):
                    self._prepare_directory(task)
                    self.status = TaskMetadata(
                        version=PROTOCOL_VERSION,
                        task_id=task.task_id,
                        run_id=task.context.run_id,
                        task_type=task.task_type,
                        reg_name=task.reg_name,
                        source=task.context.source,
                        report_kind=task.report_kind,
                        input_params=task.input_params.model_dump(mode="json"),
                        pid=task.pid,
                        created_at=task.created_at,
                        log_path=task.log_path,
                    )
                    status = self.status
                    task._metadata = status
                    task._persist_metadata = self._publish
                    task._progress = self.progress
                    self._publish()
                    task.logger.info(f"Task started task_id={task.task_id} task_type={task.task_type.value}")
                    status.state = TaskState.RUNNING
                    status.started_at = datetime.now(UTC)
                    self._publish()
                for step in task.build_task_steps():
                    self._run_step(step)
            except BaseException:
                self._close_after_error(task)
                raise
            else:
                task.close()
            task.prepare_output()
            output = task.output
            exit_code = task.exit_code(output)
            status.exit_code = exit_code
            status.output_params = output
            status.state = TaskState.SUCCEEDED if exit_code == 0 else TaskState.FAILED
            status.error = "" if exit_code == 0 else f"Task exited with code {exit_code}"
            status.finished_at = datetime.now(UTC)
            task.logger.info(
                f"Task completed task_id={task.task_id} exit_code={exit_code} "
                f"elapsed_seconds={perf_counter() - started:.3f}",
            )
            self._publish()
            return status
        except BaseException as exc:
            # Preparation rejection must never publish into another run's directory.
            if self.status is None:
                raise
            status = self.status
            try:
                task.on_failure(exc)
            except Exception:
                task.logger.exception("Task failure callback failed")
            status.state = TaskState.FAILED
            status.exit_code = 1
            status.error = f"{type(exc).__name__}: {exc}"
            status.finished_at = datetime.now(UTC)
            task.logger.exception(
                f"Task failed task_id={task.task_id} elapsed_seconds={perf_counter() - started:.3f} "
                f"error={type(exc).__name__}",
            )
            self._publish()
            raise
        finally:
            task._progress = None
            task._persist_metadata = None
            self.task = None
            self.status = None
            self.step = None
