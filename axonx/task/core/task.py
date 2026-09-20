"""Public authoring contract for synchronous Tasks."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar, TypeAlias
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ...constants import (
    AXONX_DEFAULT_TIMEZONE,
    TASK_ID_SEPARATOR,
    TASK_ID_TIMESTAMP_FORMAT,
)
from ...enums import ComponentEnum, TaskType
from ...utils import get_log_path, get_logger
from ..storage.workspace import METADATA_FILE, task_path
from .context import TaskContext
from .identity import validate_registration_name
from .params import BaseInputParams, BaseOutputParams

TaskStep: TypeAlias = Callable[[], None]


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
        task_id: str | None = None,
        run_id: str | None = None,
        created_at: datetime | None = None,
    ):
        self.input_params = self.input_cls.model_validate(input_params)
        workspace = Path(workspace_path).expanduser().resolve()
        if reg_name is None:
            raise ValueError(f"Task {type(self).__name__} requires a registration name")
        registration_name = validate_registration_name(reg_name)

        try:
            task_timezone = ZoneInfo(timezone)
        except ZoneInfoNotFoundError:
            raise ValueError(f"Unknown timezone: {timezone!r}") from None
        created_at = created_at or datetime.now(task_timezone)

        parts = [self.task_type.value, registration_name, self.input_params.task_name]
        if self.input_params.include_time:
            # Microsecond precision prevents ordinary concurrent submissions with
            # the same human name from claiming the same workspace directory.
            parts.append(created_at.strftime(TASK_ID_TIMESTAMP_FORMAT))
        generated_task_id = TASK_ID_SEPARATOR.join(parts)
        task_id = task_id or generated_task_id
        if task_id != generated_task_id:
            raise ValueError(f"Assigned Task ID does not match its inputs: {task_id!r}")
        self.context = TaskContext(
            workspace_path=workspace,
            registration_name=registration_name,
            task_id=task_id,
            run_id=run_id or uuid4().hex,
            created_at=created_at,
            logger=get_logger(type(self).__name__),
        )
        self.state: dict[str, Any] = {}
        self._output_params: BaseOutputParams | None = None

        self.pid = os.getpid()
        self.log_path = str(get_log_path() or "")
        self._progress: Callable[[float], None] | None = None

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
    def metadata_path(self) -> Path:
        return self.task_dir / METADATA_FILE

    def source_task_dir(self, task_id: str) -> Path:
        return task_path(self.workspace_path, task_id)

    @staticmethod
    def normalize_yyyymmdd(value: object, *, optional: bool = False) -> str | None:
        if optional and (
            value is None or isinstance(value, str) and value.lower() in {"", "none"}
        ):
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
    def output(self) -> dict:
        return self.output_params.model_dump(mode="json", by_alias=True)

    def prepare_output(self) -> BaseOutputParams:
        """Build one typed result after all steps complete."""
        output = self.build_output_params()
        if not isinstance(output, self.output_cls):
            raise TypeError(
                f"{type(self).__name__}.build_output_params must return {self.output_cls.__name__}"
            )
        self._output_params = output
        return output

    def report_progress(self, percentage: float) -> None:
        if self._progress is None:
            raise RuntimeError("Progress can only be reported while a Task is running")
        self._progress(percentage)

    @staticmethod
    def exit_code(_output: dict) -> int:
        return 0
