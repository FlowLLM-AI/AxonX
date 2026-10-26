"""Public authoring contract for synchronous Tasks."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar, TypeAlias
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ...common.logging import get_log_path, get_logger
from ..constants import TASK_ID_SEPARATOR
from .clock import WindowClock
from .context import TaskContext
from ..task_enums import TaskCategory, TaskType
from ..identity import (
    generated_task_name,
    parse_source_tasks,
    validate_registration_name,
)
from ..models.lifecycle import TaskMetadata, TaskSource
from ..models.params import BaseInputParams, BaseOutputParams
from ..storage.workspace import (
    METADATA_FILE,
    PERSISTENT_DIR,
    read_task_metadata,
    task_id_from_path,
    task_path,
)

TaskStep: TypeAlias = Callable[[], None]


class BaseTask(ABC):
    """Execute ordered synchronous steps with typed input and output."""

    task_type: ClassVar[TaskType] = TaskType.BASE
    input_cls: ClassVar[type[BaseInputParams]] = BaseInputParams
    output_cls: ClassVar[type[BaseOutputParams]] = BaseOutputParams
    category: ClassVar[TaskCategory | None] = None
    report_kind: ClassVar[str | None] = None

    def __init__(
        self,
        input_params: BaseInputParams | dict,
        *,
        workspace_path: str | Path,
        reg_name: str | None = None,
        timezone: str = "Asia/Shanghai",
        task_id: str | None = None,
        created_at: datetime | None = None,
        source: TaskSource | None = None,
        parent_task_id: str | None = None,
        execution_target: str | None = None,
        clock: WindowClock | None = None,
        task_resolver: Callable[[str], type[BaseTask]] | None = None,
    ):
        self.input_params = self.input_cls.model_validate(input_params)
        workspace_path = Path(workspace_path).expanduser().resolve()
        self.task_resolver = task_resolver
        if reg_name is None:
            raise ValueError(f"Task {type(self).__name__} requires a registration name")
        registration_name = validate_registration_name(reg_name)

        try:
            task_timezone = ZoneInfo(timezone)
        except ZoneInfoNotFoundError:
            raise ValueError(f"Unknown timezone: {timezone!r}") from None
        created_at = created_at or datetime.now(task_timezone)

        self.is_generated_name = self.input_params.task_name is None
        resolved_name = self.input_params.task_name or generated_task_name(created_at)
        self.input_params.task_name = resolved_name
        generated_task_id = TASK_ID_SEPARATOR.join((self.task_type.value, registration_name, resolved_name))
        task_id = task_id or generated_task_id
        if task_id != generated_task_id:
            raise ValueError(f"Assigned Task ID does not match its inputs: {task_id!r}")
        if task_id in parse_source_tasks(self.input_params.source_tasks):
            raise ValueError("A Task cannot use its own Task ID as an upstream source")
        self.context = TaskContext(
            workspace_path=workspace_path,
            registration_name=registration_name,
            task_id=task_id,
            created_at=created_at,
            logger=get_logger(type(self).__name__),
            source=source or TaskSource(kind="exec"),
            parent_task_id=parent_task_id,
            execution_target=execution_target,
        )
        self.state: dict[str, Any] = {}
        self.clock = clock if clock is not None else getattr(self, "clock", WindowClock())
        self._output_params: BaseOutputParams | None = None

        self.log_path = str(get_log_path() or "")
        self._progress: Callable[..., None] | None = None
        self._persist_metadata: Callable[[], None] | None = None
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
    def logger(self):
        return self.context.logger

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
        """Publish changes to the shared record while its Runner owns execution."""
        if self._persist_metadata is None:
            raise RuntimeError("Task metadata can only be persisted inside the TaskRunner")
        self._persist_metadata()  # pylint: disable=not-callable

    def source_task_dir(self, task_id: str) -> Path:
        directory = task_path(self.workspace_path, task_id)
        metadata = read_task_metadata(directory, task_id)
        if metadata is not None and metadata.replica is not None:
            raise ValueError("Display replicas cannot be used as research inputs")
        return directory

    def resolve_workspace_path(self, path: str | Path) -> Path:
        candidate = Path(path).expanduser()
        resolved = (candidate if candidate.is_absolute() else self.workspace_path / candidate).resolve()
        owner = task_id_from_path(self.workspace_path, str(resolved))
        if owner is not None:
            self.source_task_dir(owner)
        return resolved

    def on_failure(self, error: BaseException) -> None:
        """Record business-specific failure details; the runner owns task status."""

    def close(self) -> None:
        """Release owned resources after steps complete or fail."""

    @abstractmethod
    def build_task_steps(self) -> Iterable[TaskStep]:
        """Yield synchronous callables in execution order."""

    @abstractmethod
    def build_output_params(self) -> BaseOutputParams:
        """Return the explicit, validated result after all steps complete."""

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
        from ..storage.artifacts import artifact_path

        record = self.output_params.artifacts[name].model_dump()
        return artifact_path(self.task_dir, {"output_params": {"artifacts": {name: record}}}, name)

    def prepare_output(self) -> BaseOutputParams:
        """Build one typed result after all steps complete."""
        output = self.build_output_params()
        if not isinstance(output, self.output_cls):
            raise TypeError(f"{type(self).__name__}.build_output_params must return {self.output_cls.__name__}")
        self._output_params = output
        return output

    def report_progress(
        self,
        percentage: float | None = None,
        *,
        name: str | None = None,
        **changes: Any,
    ) -> None:
        """Update the executing step, or a named concurrent substep.

        Named substeps are validated and throttled by the Runner. Stop and join
        background producers before this Task's lifecycle ends.
        """
        progress = self._progress
        if progress is None:
            raise RuntimeError("Progress can only be reported inside the TaskRunner")
        progress(percentage, name=name, **changes)  # pylint: disable=not-callable

    @staticmethod
    def exit_code(_output: dict) -> int:
        return 0
