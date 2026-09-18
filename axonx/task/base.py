"""Base types for synchronous tasks."""

from __future__ import annotations

import os
import secrets
import string
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, TypeAlias
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..constants import AXONX_DEFAULT_TIMEZONE
from ..enums import ComponentEnum, TaskType
from ..schema import TaskStatus
from ..utils import get_log_path, get_logger
from .identity import registration_name, task_type_from_id

if TYPE_CHECKING:
    from .runner import TaskRunner

TaskStep: TypeAlias = Callable[[], None]
_TASK_NAME_ALPHABET = string.ascii_letters + string.digits


def _short_task_name() -> str:
    return "".join(secrets.choice(_TASK_NAME_ALPHABET) for _ in range(4))


class BaseInputParams(BaseModel):
    """Validated user supplied parameters for one task invocation."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    task_name: str = Field(default_factory=_short_task_name, pattern=r"^[A-Za-z0-9-]{1,32}$")
    include_time: bool = True
    source_tasks: list[str] = Field(default_factory=list)

    @field_validator("source_tasks")
    @classmethod
    def validate_source_tasks(cls, sources: list[str]) -> list[str]:
        for task_id in sources:
            task_type_from_id(task_id)
        if len(sources) != len(set(sources)):
            raise ValueError("source_tasks contains duplicate task IDs")
        return sources

    def source_task(self, task_type: TaskType) -> str:
        matches = [task_id for task_id in self.source_tasks if task_type_from_id(task_id) == task_type]
        if len(matches) == 1:
            return matches[0]
        if matches:
            raise ValueError(f"Multiple source tasks of type: {task_type.value}")
        raise ValueError(f"Missing source task: {task_type.value}")


class BaseOutputParams(BaseModel):
    """Validated task result, including any produced artifacts."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    artifacts: dict[str, dict[str, Any]] = Field(default_factory=dict)


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
        timezone: str = AXONX_DEFAULT_TIMEZONE,
    ):
        self.input_params = self.input_cls.model_validate(input_params)
        self.workspace_path = Path(workspace_path).expanduser().resolve()
        self.context: dict[str, Any] = {"workspace_path": self.workspace_path}
        self.logger = get_logger(type(self).__name__)

        self.reg_name = registration_name(type(self), reg_name)

        try:
            task_timezone = ZoneInfo(timezone)
        except ZoneInfoNotFoundError:
            raise ValueError(f"Unknown timezone: {timezone!r}") from None
        self.created_at = datetime.now(task_timezone)

        parts = [self.task_type.value, self.reg_name, self.input_params.task_name]
        if self.input_params.include_time:
            parts.append(f"{self.created_at:%Y%m%d%H}")
        self.task_id = "#".join(parts)
        self._output_params: BaseOutputParams | None = None

        self._status = TaskStatus(
            task_id=self.task_id,
            task_type=self.task_type,
            task_name=self.reg_name,
            config=self.input_params.model_dump(mode="json"),
            pid=os.getpid(),
            created_at=self.created_at,
            log_path=str(get_log_path() or ""),
        )
        self._runner: TaskRunner | None = None

    @property
    def status(self) -> TaskStatus:
        return self._status

    @property
    def task_dir(self) -> Path:
        return self.workspace_path / self.task_type.value / self.task_id

    @property
    def metadata_path(self) -> Path:
        return self.task_dir / "metadata.json"

    def source_task_dir(self, task_id: str) -> Path:
        return self.workspace_path / task_type_from_id(task_id).value / task_id

    @staticmethod
    def normalize_yyyymmdd(value: object, *, optional: bool = False) -> str | None:
        if optional and (value is None or isinstance(value, str) and value.lower() in {"", "none"}):
            return None
        normalized = str(value)
        try:
            parsed = datetime.strptime(normalized, "%Y%m%d")
        except ValueError as exc:
            raise ValueError(f"必须是有效 YYYYMMDD: {normalized}") from exc
        if parsed.strftime("%Y%m%d") != normalized:
            raise ValueError(f"必须是有效 YYYYMMDD: {normalized}")
        return normalized

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
    def output_params(self) -> BaseOutputParams:
        if self._output_params is None:
            raise RuntimeError("Task output is unavailable before execution completes")
        return self._output_params

    @property
    def output(self) -> dict[str, Any]:
        return self.output_params.model_dump(mode="json", by_alias=True)

    def prepare_output(self) -> BaseOutputParams:
        """Build one typed result after all steps complete."""
        output = self.build_output_params()
        if not isinstance(output, self.output_cls):
            raise TypeError(f"{type(self).__name__}.build_output_params must return {self.output_cls.__name__}")
        self._output_params = output
        return output

    def execute(self, *, emit: Callable[[TaskStatus], None] | None = None) -> dict[str, Any]:
        from .runner import TaskRunner

        TaskRunner(emit).run(self)
        return self.output

    def report_progress(self, percentage: float) -> None:
        if self._runner is None:
            raise RuntimeError("Progress can only be reported while a Task is running")
        self._runner.progress(percentage)

    @staticmethod
    def exit_code(_output: dict[str, Any]) -> int:
        return 0
