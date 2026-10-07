"""Thin synchronous composition of independently recorded Tasks."""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Literal
from uuid import uuid4

from pydantic import Field

from ..constants import AXONX_DEFAULT_TIMEZONE
from ..enums import TaskState
from .core import BaseOutputParams, BaseTask, validate_registration_name
from .storage.artifacts import artifact_record
from .storage.composition import COMPOSITION_FILE, ChildTaskRecord, TaskComposition, write_composition
from .storage.workspace import TaskStatus, is_task_directory, read_status, write_status


@dataclass(frozen=True)
class ChildTaskResult:
    """An invocation snapshot plus its typed output, when output was built."""

    record: ChildTaskRecord
    output_params: BaseOutputParams | None = None

    @property
    def task_id(self) -> str:
        if self.record.task_id is None:
            raise RuntimeError("Child Task was not constructed")
        return self.record.task_id

    @property
    def run_id(self) -> str:
        return self.record.run_id

    @property
    def success(self) -> bool:
        return self.record.state == TaskState.SUCCEEDED

    @property
    def output(self) -> dict:
        if self.output_params is None:
            raise RuntimeError("Child Task output is unavailable")
        return self.output_params.model_dump(mode="json", by_alias=True)


class ChildTaskError(RuntimeError):
    """Fail-fast child error with a retained invocation result."""

    def __init__(self, result: ChildTaskResult):
        self.result = result
        super().__init__(f"Child Task {result.record.node_name!r} failed: {result.record.error}")


class BaseCompositeOutputParams(BaseOutputParams):
    composition_file: str
    children: list[ChildTaskRecord] = Field(default_factory=list)


class BaseCompositeTask(BaseTask, ABC):
    """Compose registered Tasks with ordinary Python sequencing and loops.

    Children run synchronously in this worker with independent identities and
    records. ``on_error='continue'`` permits later work but does not turn the
    overall run into a success. Cancellation is performed through the parent.
    """

    output_cls = BaseCompositeOutputParams

    def __init__(self, *args, timezone: str = AXONX_DEFAULT_TIMEZONE, **kwargs):
        super().__init__(*args, timezone=timezone, **kwargs)
        self._child_timezone = timezone
        self._composition = TaskComposition(task_id=self.task_id, run_id=self.context.run_id)

    @property
    def children(self) -> tuple[ChildTaskRecord, ...]:
        """Expose defensive snapshots, never mutable runtime records."""
        return tuple(child.model_copy(deep=True) for child in self._composition.children)

    def run_task(
        self,
        task: str,
        *,
        node_name: str | None = None,
        on_error: Literal["stop", "continue"] = "stop",
        **inputs,
    ) -> ChildTaskResult:
        """Run one child through its full lifecycle and bind its output explicitly."""
        if self._progress is None:
            raise RuntimeError("Child Tasks must run inside the parent TaskRunner")
        validate_registration_name(task)
        node_name = validate_registration_name(node_name or task)
        if on_error not in {"stop", "continue"}:
            raise ValueError("on_error must be 'stop' or 'continue'")
        if "task_name" in inputs:
            raise ValueError("Child task_name is owned by the composition runtime")
        previous = [child for child in self._composition.children if child.node_name == node_name]
        if any(child.task != task for child in previous):
            raise ValueError(f"Node {node_name!r} already refers to another Task")
        record = ChildTaskRecord(node_name=node_name, attempt=len(previous) + 1, task=task, run_id=uuid4().hex)
        self._composition.children.append(record)
        self._write_composition()
        output = None
        try:
            output = self._run_child(record, inputs)
        except BaseException as exc:
            record.state = TaskState.FAILED
            record.exit_code = record.exit_code or 1
            record.error = f"{type(exc).__name__}: {exc}"
            self._write_composition()
            # Interrupts and exits must never be swallowed by continue-on-error.
            if not isinstance(exc, Exception):
                raise
            result = ChildTaskResult(record.model_copy(deep=True))
            if on_error == "stop":
                raise ChildTaskError(result) from exc
            return result
        self._write_composition()
        result = ChildTaskResult(record.model_copy(deep=True), output)
        if not result.success and on_error == "stop":
            raise ChildTaskError(result)
        return result

    def _run_child(self, record: ChildTaskRecord, inputs: dict) -> BaseOutputParams:
        # Keep runtime/catalog imports out of the authoring module's import graph.
        from .catalog.resolver import resolve_task
        from .runtime.runner import TaskRunner

        identity = f"{self.task_id}\0{self.context.run_id}\0{record.node_name}\0{record.attempt}"
        name = "c-" + sha256(identity.encode()).hexdigest()[:30]
        child = resolve_task(record.task)(
            {**inputs, "task_name": name},
            workspace_path=self.workspace_path,
            reg_name=record.task,
            timezone=self._child_timezone,
            run_id=record.run_id,
        )
        queued = None
        runner_started = False
        try:
            if child.task_dir.parent.is_symlink():
                raise ValueError("Child Task type directory cannot be a symlink")
            # Claim exclusively before handing a queued status to the Runner.
            # A collision must not replace another run or its results.
            child.task_dir.mkdir(parents=True, exist_ok=False)
            record.task_id = child.task_id
            queued = TaskStatus(
                task_id=child.task_id,
                run_id=record.run_id,
                task_type=child.task_type,
                task_name=record.task,
                config=child.input_params.model_dump(mode="json"),
                pid=child.pid,
                created_at=child.created_at,
                log_path=child.log_path,
            )
            self._write_composition()
            write_status(child.task_dir, queued)
            record.state = TaskState.RUNNING
            self._write_composition()
            runner_started = True
            status = TaskRunner().run(child)
        except BaseException as exc:
            if not runner_started:
                try:
                    child.close()
                except Exception:
                    child.logger.exception("Child Task resource cleanup failed")
            status = None
            if record.task_id is not None and is_task_directory(child.task_dir, strict_io=True):
                # The first queued write may itself have failed. Keep a status
                # for our claimed directory without recreating deleted runs.
                status = read_status(child.task_dir, child.task_id, strict_io=True) or queued
            if status is not None and status.run_id == record.run_id:
                if not status.state.is_terminal:
                    status.state = TaskState.FAILED
                    status.exit_code = 1
                    status.error = f"{type(exc).__name__}: {exc}"
                    status.finished_at = datetime.now(UTC)
                    write_status(child.task_dir, status)
                record.exit_code = status.exit_code
            raise
        record.state, record.exit_code, record.error = status.state, status.exit_code, status.error
        return child.output_params

    def _write_composition(self) -> None:
        write_composition(self.task_dir, self._composition)

    def composition_output(self) -> dict:
        """Build the common output envelope for Tasks adding business result fields."""
        self._write_composition()
        path = self.task_dir / COMPOSITION_FILE
        return {
            "composition_file": str(path),
            "children": list(self.children),
            "artifacts": {"composition": artifact_record(path, self.task_dir)},
        }

    def build_output_params(self) -> BaseCompositeOutputParams:
        return self.output_cls(**self.composition_output())

    # Unlike a leaf's static exit code, composition aggregates owned run records.
    def exit_code(self, _output: dict) -> int:  # pylint: disable=arguments-differ
        return next(
            (child.exit_code or 1 for child in self._composition.children if child.state != TaskState.SUCCEEDED), 0
        )
