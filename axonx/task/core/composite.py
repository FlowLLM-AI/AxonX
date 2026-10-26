"""Thin synchronous composition of independently recorded Tasks."""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass
from typing import Literal

from .task import BaseTask
from ..task_enums import TaskState, TaskType
from ..identity import validate_registration_name
from ..models.lifecycle import ChildTaskRecord
from ..models.params import BaseOutputParams


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


class BaseCompositeTask(BaseTask, ABC):
    """Compose registered Tasks with ordinary Python sequencing and loops.

    Children run synchronously in this worker, inheriting the parent name and
    retaining invocation snapshots. ``on_error='continue'`` permits later work but does not turn the
    overall run into a success. Cancellation is performed through the parent.
    """

    task_type = TaskType.COMPOSITE
    output_cls = BaseOutputParams

    def __init__(self, *args, timezone: str = "Asia/Shanghai", **kwargs):
        super().__init__(*args, timezone=timezone, **kwargs)
        self._child_timezone = timezone

    @property
    def children(self) -> tuple[ChildTaskRecord, ...]:
        """Expose defensive snapshots, never mutable runtime records."""
        return tuple(child.model_copy(deep=True) for child in self._metadata.children) if self._metadata else ()

    def run_task(
        self,
        task: str,
        *,
        node_name: str | None = None,
        on_error: Literal["stop", "continue"] = "stop",
        task_name: str | None = None,
        **inputs,
    ) -> ChildTaskResult:
        """Run one child through its full lifecycle and bind its output explicitly."""
        if self._progress is None:
            raise RuntimeError("Child Tasks must run inside the parent TaskRunner")
        validate_registration_name(task)
        node_name = validate_registration_name(node_name or (f"{task_name}-{task}" if task_name is not None else task))
        if on_error not in {"stop", "continue"}:
            raise ValueError("on_error must be 'stop' or 'continue'")

        if task_name is not None:
            inputs["task_name"] = task_name
        previous = [child for child in self.metadata.children if child.node_name == node_name]
        if any(child.task != task for child in previous):
            raise ValueError(f"Node {node_name!r} already refers to another Task")
        record = ChildTaskRecord(
            node_name=node_name,
            attempt=len(previous) + 1,
            task=task,
        )
        self.metadata.children.append(record)
        self.persist_metadata()
        try:
            output = self._run_child(record, inputs)
        except BaseException as exc:
            record.state = TaskState.FAILED
            record.exit_code = 1
            record.error = f"{type(exc).__name__}: {exc}"
            self.persist_metadata()
            # Interrupts and exits must never be swallowed by continue-on-error.
            if not isinstance(exc, Exception):
                raise
            result = ChildTaskResult(record.model_copy(deep=True))
            if on_error == "stop":
                raise ChildTaskError(result) from exc
            return result
        self.persist_metadata()
        result = ChildTaskResult(record.model_copy(deep=True), output)
        if not result.success and on_error == "stop":
            raise ChildTaskError(result)
        return result

    def _run_child(self, record: ChildTaskRecord, inputs: dict) -> BaseOutputParams:
        if self.task_resolver is None:
            raise RuntimeError("Composite Tasks require a task resolver")
        from ..runtime.runner import TaskRunner

        child = self.task_resolver(record.task)(
            {"task_name": self.input_params.task_name, **inputs},
            workspace_path=self.workspace_path,
            reg_name=record.task,
            timezone=self._child_timezone,
            source=self.context.source,
            parent_task_id=self.task_id,
            execution_target=self.context.execution_target,
            task_resolver=self.task_resolver,
        )
        child.clock = self.clock
        record.task_id = child.task_id
        record.state = TaskState.RUNNING
        try:
            self.persist_metadata()
        except BaseException:
            try:
                child.close()
            except Exception:
                child.logger.exception("Child Task resource cleanup failed")
            raise

        def observe(started_at):
            record.started_at = started_at
            self.persist_metadata()

        status = TaskRunner(on_started=observe).run(child)
        record.state, record.exit_code, record.error = (
            status.state,
            status.exit_code,
            status.error,
        )
        return child.output_params

    def build_output_params(self) -> BaseOutputParams:
        return self.output_cls()

    # Unlike a leaf's static exit code, composition aggregates child outcomes.
    def exit_code(self, _output: dict) -> int:  # pylint: disable=arguments-differ
        return next(
            (child.exit_code or 1 for child in self.metadata.children if child.state != TaskState.SUCCEEDED),
            0,
        )
