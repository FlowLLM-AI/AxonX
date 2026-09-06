"""Durable snapshots for task runs and their individual steps."""

from typing import Any
from pydantic import BaseModel, Field

from ..enumeration import TaskState


class TaskStep(BaseModel):
    """Describe the name and optional completion percentage of one step."""

    name: str = Field(min_length=1)
    percentage: float | None = Field(default=None, ge=0, le=100)


class TaskRun(BaseModel):
    """Represent the complete persisted state of one task execution."""

    id: str
    task: str
    state: TaskState = TaskState.QUEUED
    pid: int | None = None
    created_at: float
    started_at: float | None = None
    finished_at: float | None = None
    task_steps: list[TaskStep] = Field(default_factory=list)
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    exit_code: int | None = None
