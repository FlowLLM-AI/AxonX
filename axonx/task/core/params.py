"""Validated input and output envelopes shared by every Task."""

from __future__ import annotations

import secrets
import string
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ...constants import TASK_NAME_PATTERN
from ...enums import TaskType
from .identity import task_type_from_id

_TASK_NAME_ALPHABET = string.ascii_letters + string.digits


def _short_task_name() -> str:
    return "".join(secrets.choice(_TASK_NAME_ALPHABET) for _ in range(4))


class BaseInputParams(BaseModel):
    """Validated user-supplied parameters for one Task invocation."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    task_name: str = Field(default_factory=_short_task_name, pattern=TASK_NAME_PATTERN)
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
    """Validated Task result, including any produced artifacts."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    artifacts: dict[str, dict[str, Any]] = Field(default_factory=dict)
