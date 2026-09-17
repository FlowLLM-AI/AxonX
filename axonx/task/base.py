"""Base types for synchronous tasks."""

from __future__ import annotations

import os
import re
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path
from typing import Any, ClassVar, TypeAlias
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, SerializeAsAny

from ..constants import PLUGIN_MANIFEST
from ..enums import ComponentEnum, TaskType
from ..plugin.manifest import parse_plugin_manifest
from ..schema import TaskStatus
from ..utils import get_log_path, get_logger
from .status_manager import StatusCallback, TaskStatusManager

TaskStep: TypeAlias = Callable[[], None]
_REG_NAME = re.compile(r"^[A-Za-z0-9_-]+$")


def _manifest_registration_name(task_class: type["BaseTask"]) -> str | None:
    """Find a directly constructed plugin Task's name in its package manifest."""
    module = task_class.__module__
    target = f"{module}:{task_class.__qualname__}"
    package = module.rpartition(".")[0]
    while package:
        manifest_file = files(package).joinpath(PLUGIN_MANIFEST)
        if manifest_file.is_file():
            manifest = parse_plugin_manifest(manifest_file.read_text(encoding="utf-8"), package)
            names = [name for name, value in manifest.tasks.items() if value == target]
            if len(names) > 1:
                raise ValueError(f"Task {task_class.__name__} has multiple registration names; pass reg_name")
            if names:
                return names[0]
        package = package.rpartition(".")[0]
    return None


class BaseInputParams(BaseModel):
    """Validated user supplied parameters for one task invocation."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    task_name: str = Field(default_factory=lambda: uuid4().hex[:8], pattern=r"^[A-Za-z0-9-]{1,32}$")
    include_time: bool = True


class BaseOutputParams(BaseModel):
    """Validated task result, including any produced artifacts."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    artifacts: dict[str, dict[str, Any]] = Field(default_factory=dict)


class TaskMetadata(BaseModel):
    """Common persisted envelope around task specific input and output."""

    schema_version: int = 2
    task_id: str
    reg_name: str
    created_at: datetime
    task_type: TaskType
    input_params: SerializeAsAny[BaseInputParams]
    output_params: SerializeAsAny[BaseOutputParams]
    source_tasks: dict[str, str] = Field(default_factory=dict)


class BaseTask(ABC):
    """Execute ordered synchronous steps with typed input and output."""

    component_type = ComponentEnum.TASK
    task_type: ClassVar[TaskType] = TaskType.BASE
    input_cls: ClassVar[type[BaseInputParams]] = BaseInputParams
    output_cls: ClassVar[type[BaseOutputParams]] = BaseOutputParams

    def __init__(
        self,
        input_params: BaseInputParams | dict,
        *,
        workspace_path: str | Path,
        reg_name: str | None = None,
    ):
        self.input_params = self.input_cls.model_validate(input_params)
        self.workspace_path = Path(workspace_path).expanduser().resolve()
        self.context: dict[str, Any] = {"workspace_path": self.workspace_path}
        self.logger = get_logger(type(self).__name__)
        if reg_name is None:
            from ..components.registry import R

            names = [name for name, task_cls in R.get_all(ComponentEnum.TASK).items() if task_cls is type(self)]
            if len(names) > 1:
                raise ValueError(f"Task {type(self).__name__} has multiple registration names; pass reg_name")
            reg_name = names[0] if names else _manifest_registration_name(type(self))
        name = reg_name
        if not name:
            raise ValueError(f"Task {type(self).__name__} has no registration name")
        if not _REG_NAME.fullmatch(name):
            raise ValueError(f"Invalid Task registration name: {name!r}")
        self.reg_name = name
        self.created_at = datetime.now(UTC)
        parts = [name, self.input_params.task_name]
        if self.input_params.include_time:
            parts.append(f"{self.created_at:%Y%m%d%H%M%S}")
        self.task_id = "#".join(parts)
        self.source_tasks = {
            key: value for key, value in self.input_params.model_dump().items()
            if key.endswith("_task_id") and isinstance(value, str) and value
        }
        self.task_metadata: TaskMetadata | None = None
        self._output_params: BaseOutputParams | None = None
        self._status = TaskStatus(
            task_id=self.task_id,
            task_type=self.task_type,
            task_name=name,
            config=self.input_params.model_dump(mode="json"),
            pid=os.getpid(),
            log_path=str(get_log_path() or ""),
        )
        self._status_manager: TaskStatusManager | None = None

    @property
    def status(self) -> TaskStatus:
        return self._status

    def resolve_workspace_path(self, path: str | Path) -> Path:
        path = Path(path).expanduser()
        return (path if path.is_absolute() else self.workspace_path / path).resolve()

    @abstractmethod
    def build_task_steps(self) -> Iterable[TaskStep]:
        """Yield synchronous callables in execution order."""

    @abstractmethod
    def build_output_params(self) -> BaseOutputParams:
        """Return the explicit, validated result after all steps complete."""

    @property
    def output(self) -> dict[str, Any]:
        if self._output_params is None:
            raise RuntimeError("Task output is unavailable before execution completes")
        return self._output_params.model_dump(mode="json", by_alias=True)

    def prepare_output(self) -> None:
        """Build one typed result and persist its frontend metadata."""
        output = self.build_output_params()
        if not isinstance(output, self.output_cls):
            raise TypeError(f"{type(self).__name__}.build_output_params must return {self.output_cls.__name__}")
        self._output_params = output
        self.task_metadata = TaskMetadata(
            task_id=self.task_id,
            reg_name=self.reg_name,
            created_at=self.created_at,
            task_type=self.task_type,
            input_params=self.input_params,
            output_params=output,
            source_tasks=self.source_tasks,
        )
        metadata_file = getattr(output, "metadata_file", None)
        if metadata_file is not None:
            from .core.artifacts import write_metadata

            write_metadata(Path(metadata_file), self.task_metadata)

    def prepare_status(self) -> TaskStatus:
        return self._status.model_copy(deep=True)

    def execute(self, *, emit: StatusCallback | None = None) -> dict[str, Any]:
        from .runner import TaskRunner

        self._status = TaskRunner(emit).run(self)
        return self.output

    def report_progress(self, percentage: float) -> None:
        if self._status_manager is None:
            raise RuntimeError("Progress can only be reported while a Task is running")
        self._status_manager.progress(percentage)

    def _bind_status_manager(self, manager: TaskStatusManager | None) -> None:
        if manager is not None:
            self._status = manager.status
        self._status_manager = manager

    def exit_code(self, _output: dict[str, Any]) -> int:
        return 0
