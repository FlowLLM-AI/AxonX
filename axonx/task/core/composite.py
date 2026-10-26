"""Thin synchronous composition of independently recorded Tasks."""

from __future__ import annotations

from abc import ABC
from typing import Literal

from ..models.identity import TaskState, TaskType, validate_registration_name
from ..models.lifecycle import ChildTaskRecord, ChildTaskResult
from ..models.params import BaseOutputParams
from .task import BaseTask


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
        execute_child = self._execute_child
        if execute_child is None:
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
            output = execute_child(record, inputs)  # pylint: disable=not-callable
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

    def build_output_params(self) -> BaseOutputParams:
        return self.output_cls()

    # Unlike a leaf's static exit code, composition aggregates child outcomes.
    def exit_code(self, _output: dict) -> int:  # pylint: disable=arguments-differ
        return next(
            (child.exit_code or 1 for child in self.metadata.children if child.state != TaskState.SUCCEEDED),
            0,
        )
