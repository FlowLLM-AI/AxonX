"""Domain execution and shared operations."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field, TypeAdapter

from ..common.logs import LogEvent
from .models.lifecycle import TaskStepStatus


class ProgressEvent(TaskStepStatus):
    kind: Literal["progress"] = "progress"

    @classmethod
    def from_status(cls, status: Any) -> ProgressEvent:
        return cls.model_validate(status, from_attributes=True)


type TaskEvent = Annotated[ProgressEvent | LogEvent, Field(discriminator="kind")]


TASK_EVENT_ADAPTER: TypeAdapter[TaskEvent] = TypeAdapter(TaskEvent)
