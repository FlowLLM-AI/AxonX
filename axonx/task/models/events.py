"""Task progress and logs, their query chunks and discriminated stream events."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, TypeAdapter

from .base import TaskModel
from .lifecycle import TaskStepStatus


class LogChunk(TaskModel):
    content: str = ""
    start_offset: int = 0
    next_offset: int = 0
    file_size: int = 0
    has_more_before: bool = False
    has_more_after: bool = False
    reset: bool = False


class LogEvent(LogChunk):
    kind: Literal["log"] = "log"
    channel: str = "task"

    @classmethod
    def from_chunk(cls, chunk: LogChunk) -> LogEvent:
        return cls.model_validate(chunk, from_attributes=True)


class ProgressEvent(TaskStepStatus):
    kind: Literal["progress"] = "progress"

    @classmethod
    def from_status(cls, status: TaskStepStatus) -> ProgressEvent:
        return cls.model_validate(status, from_attributes=True)


type TaskEvent = Annotated[ProgressEvent | LogEvent, Field(discriminator="kind")]


TASK_EVENT_ADAPTER: TypeAdapter[TaskEvent] = TypeAdapter(TaskEvent)
