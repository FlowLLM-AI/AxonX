"""Public authoring contract for synchronous Tasks."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar, Literal, TypeAlias
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ...utils.logging import get_logger
from ..models.identity import (
    TASK_ID_SEPARATOR,
    TaskState,
    TaskType,
    generated_task_name,
    validate_registration_name,
)
from ..models.lifecycle import ChildTaskRecord, ChildTaskResult, TaskContext, TaskMetadata
from ..models.params import BaseInputParams, BaseOutputParams
from ..storage.inputs import resolve_input_path, upstream_task_directory
from ..storage.workspace import (
    METADATA_FILE,
    PERSISTENT_DIR,
    resolve_relative_path,
    task_path,
)
from .clock import WindowClock

TaskStep: TypeAlias = Callable[[], None]


class ChildTaskError(RuntimeError):
    """A failed child invocation with its recorded result."""

    def __init__(self, result: ChildTaskResult):
        self.result = result
        super().__init__(f"Child Task {result.record.node_name!r} failed: {result.record.error}")


class BaseTask(ABC):
    """Execute synchronous steps and child Tasks with typed input and output."""

    task_type: ClassVar[TaskType] = TaskType.BASE
    input_cls: ClassVar[type[BaseInputParams]] = BaseInputParams
    output_cls: ClassVar[type[BaseOutputParams]] = BaseOutputParams
    report_kind: ClassVar[str | None] = None

    def __init__(
        self,
        input_params: BaseInputParams | dict,
        *,
        workspace_path: str | Path,
        reg_name: str,
        timezone: str = "Asia/Shanghai",
        created_at: datetime | None = None,
        parent_task_id: str | None = None,
        execution_target: str | None = None,
        clock: WindowClock | None = None,
    ):
        self.input_params = self.input_cls.model_validate(input_params)
        workspace_path = Path(workspace_path).expanduser().resolve()
        registration_name = validate_registration_name(reg_name)

        try:
            task_timezone = ZoneInfo(timezone)
        except ZoneInfoNotFoundError:
            raise ValueError(f"Unknown timezone: {timezone!r}") from None
        created_at = created_at or datetime.now(task_timezone)

        resolved_name = self.input_params.task_name or generated_task_name(created_at)
        self.input_params.task_name = resolved_name
        task_id = TASK_ID_SEPARATOR.join((self.task_type.value, registration_name, resolved_name))
        if task_id in self.input_params.upstream_task_ids:
            raise ValueError("A Task cannot use its own Task ID as an upstream source")
        self.context = TaskContext(
            workspace_path=workspace_path,
            registration_name=registration_name,
            task_id=task_id,
            created_at=created_at,
            timezone=timezone,
            parent_task_id=parent_task_id,
            execution_target=execution_target,
        )
        self.logger = get_logger(type(self).__name__)
        self.state: dict[str, Any] = {}
        self.clock = clock if clock is not None else WindowClock()
        self._output_params: BaseOutputParams | None = None

        self._progress: Callable[..., None] | None = None
        self._persist_metadata: Callable[[], None] | None = None
        self._execute_child: Callable[..., ChildTaskResult] | None = None
        self._metadata: TaskMetadata | None = None

    @property
    def workspace_path(self) -> Path:
        return self.context.workspace_path

    @property
    def reg_name(self) -> str:
        return self.context.registration_name

    @property
    def task_id(self) -> str:
        return self.context.task_id

    @property
    def created_at(self) -> datetime:
        return self.context.created_at

    @property
    def task_dir(self) -> Path:
        return task_path(self.workspace_path, self.task_id)

    @property
    def persistent_dir(self) -> Path:
        """Task-owned data retained across same-name reruns; deleted with the Task."""
        return self.task_dir / PERSISTENT_DIR

    @property
    def metadata_path(self) -> Path:
        return self.task_dir / METADATA_FILE

    @property
    def metadata(self) -> TaskMetadata:
        """The runtime's current record; available during and after execution."""
        if self._metadata is None:
            raise RuntimeError("Task metadata is unavailable before execution starts")
        return self._metadata

    def persist_metadata(self) -> None:
        """Publish changes to the shared record during execution."""
        if self._persist_metadata is None:
            raise RuntimeError("Task metadata can only be persisted inside the TaskExecutor")
        self._persist_metadata()  # pylint: disable=not-callable

    @property
    def children(self) -> tuple[ChildTaskRecord, ...]:
        """Return defensive snapshots of this Task's direct child invocations."""
        return tuple(child.model_copy(deep=True) for child in self._metadata.children) if self._metadata else ()

    def run_task(
        self,
        reg_name: str,
        *,
        node_name: str | None = None,
        on_error: Literal["stop", "continue"] = "stop",
        task_name: str | None = None,
        **inputs,
    ) -> ChildTaskResult:
        """Run a registered child synchronously through the bound executor.

        Children inherit this Task's name unless explicitly overridden. Repeated
        calls may replace the same Task's outputs; node names label invocations.
        Continuing permits later work. The default exit code keeps this Task
        failed; override exit_code only when the plugin has handled that failure.
        Pass upstream_task_ids explicitly when a child consumes another's output.
        """
        execute_child = self._execute_child
        if execute_child is None:
            raise RuntimeError("Child Tasks must run inside the parent TaskExecutor")
        return execute_child(  # pylint: disable=not-callable
            reg_name, node_name=node_name, on_error=on_error, task_name=task_name, inputs=inputs
        )

    def upstream_task_dir(self, task_id: str) -> Path:
        return upstream_task_directory(self.workspace_path, task_id)

    def resolve_workspace_path(self, path: str | Path) -> Path:
        return resolve_input_path(self.workspace_path, path)

    def on_failure(self, error: BaseException) -> None:
        """Record business-specific failure details; the executor owns task status."""

    def close(self) -> None:
        """Release owned resources after steps complete or fail."""

    @abstractmethod
    def build_task_steps(self) -> Iterable[TaskStep]:
        """Yield synchronous callables in execution order."""

    @abstractmethod
    def build_output_params(self) -> BaseOutputParams:
        """Build current business output; final output is built after cleanup.

        Tasks that publish incremental results also call this hook during steps.
        """

    @property
    def output_params(self) -> BaseOutputParams:
        if self._output_params is None:
            raise RuntimeError("Task output is unavailable before execution completes")
        return self._output_params

    @property
    def output(self) -> dict:
        return self.output_params.model_dump(mode="json", by_alias=True)

    def artifact_path(self, name: str) -> Path:
        """Resolve a validated published output within this Task's directory."""
        return resolve_relative_path(self.task_dir, self.output_params.artifacts[name].path)

    def _build_output(self) -> BaseOutputParams:
        """Validate output for both incremental publication and final completion."""
        output = self.build_output_params()
        if not isinstance(output, self.output_cls):
            raise TypeError(f"{type(self).__name__}.build_output_params must return {self.output_cls.__name__}")
        return output

    def publish_output(self) -> None:
        """Persist a typed business snapshot without completing the Task."""
        self.metadata.output_params.update(self._build_output().model_dump(mode="json", by_alias=True))
        self.persist_metadata()

    def report_progress(
        self,
        percentage: float | None = None,
        *,
        name: str | None = None,
        **changes: Any,
    ) -> None:
        """Update the executing step, or a named concurrent substep.

        Named substeps are validated and throttled by the runtime. Stop and join
        background producers before this Task's lifecycle ends.
        """
        progress = self._progress
        if progress is None:
            raise RuntimeError("Progress can only be reported inside the TaskExecutor")
        progress(percentage, name=name, **changes)  # pylint: disable=not-callable

    def exit_code(self, _output: dict) -> int:
        return next((child.exit_code or 1 for child in self.children if child.state != TaskState.SUCCEEDED), 0)
