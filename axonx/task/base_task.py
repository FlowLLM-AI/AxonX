"""Base types for synchronous tasks."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
import os
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from ..enumeration import ComponentEnum, TaskType
from ..schema import TaskStatus
from ..utils import get_logger

from .task_status_manager import StatusCallback, TaskStatusManager


class BaseConfig(BaseModel):
    """Forbid unknown task configuration fields by default."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    task_id: str | None = Field(default=None, frozen=True)
    task_type: TaskType | None = Field(default=None, frozen=True)
    task_id_suffix: str = Field(default_factory=lambda: uuid4().hex[-4:], pattern=r"^[A-Za-z0-9-]{1,32}$")

    def generate_task_id(self, task_type: TaskType) -> str:
        """Generate or validate the immutable Task identity."""
        if self.task_id is None and self.task_type is None:
            task_id = "#".join((task_type.value, f"{datetime.now(UTC):%Y%m%d%H%M%S}", self.task_id_suffix))
            object.__setattr__(self, "task_type", task_type)
            object.__setattr__(self, "task_id", task_id)
        elif self.task_id is None or self.task_type is None:
            raise ValueError("Task config contains an incomplete identity")
        elif self.task_type != task_type:
            raise ValueError(f"Task type mismatch: {self.task_type.value} != {task_type.value}")
        assert self.task_id is not None
        return self.task_id


class BaseTask(ABC):
    """Run a declared sequence of synchronous steps in a shared context."""

    component_type = ComponentEnum.TASK
    task_type: TaskType

    config_cls = BaseConfig
    output_keys: tuple[str, ...] = ()

    def __init__(self, config: BaseConfig | dict, **kwargs):
        if not isinstance(getattr(type(self), "task_type", None), TaskType):
            raise TypeError("Task subclasses must declare a TaskType")
        self.config = self.config_cls.model_validate(config)
        self.context = dict(kwargs)
        self.logger = get_logger(type(self).__name__)
        self.config.generate_task_id(self.task_type)
        self._status = TaskStatus(task_id=self.task_id, task_type=self.task_type, pid=os.getpid())
        self._status_manager: TaskStatusManager | None = None

    @property
    def task_id(self) -> str:
        """Return the generated Task identifier."""
        assert self.config.task_id is not None
        return self.config.task_id

    @property
    def status(self) -> TaskStatus:
        """Return this Task's latest execution status."""
        return self._status

    @abstractmethod
    def build_task_steps(self) -> Iterable[Callable[[], None]]:
        """Yield every synchronous callable in execution order."""

    @property
    def output(self) -> dict:
        """Select declared output fields from the shared task context."""
        return {key: self.context[key] for key in self.output_keys}

    def prepare_status(self) -> TaskStatus:
        """Build the initial task status before execution."""
        return self._status.model_copy(deep=True)

    def execute(self, *, emit: StatusCallback | None = None) -> dict[str, Any]:
        """Run all synchronous steps on the calling thread."""
        from .task_runner import TaskRunner

        self._status = TaskRunner(emit).run(self)
        return self.output

    def report_progress(self, percentage: float) -> None:
        """Report progress for the current step without blocking its execution."""
        if self._status_manager is None:
            raise RuntimeError("Progress can only be reported while a Task is running")
        self._status_manager.progress(percentage)

    def _bind_status_manager(self, manager: TaskStatusManager | None) -> None:
        """Bind execution-scoped status state for ``report_progress``."""
        if manager is not None:
            self._status = manager.status
        self._status_manager = manager

    def exit_code(self, _output: dict[str, Any]) -> int:
        """Return the worker exit code for a successful task output."""
        return 0
