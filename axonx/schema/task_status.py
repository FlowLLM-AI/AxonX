"""Durable task status and progress models."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from ..enumeration import TaskState, TaskType


class TaskStep(BaseModel):
    """Describe one task step and its reported progress."""

    name: str = Field(min_length=1)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    percentage: float | None = Field(default=None, ge=0, le=100)


class TaskStatus(BaseModel):
    """Represent one persisted task execution."""

    task_id: str
    task_type: TaskType
    state: TaskState = TaskState.QUEUED
    pid: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    steps: list[TaskStep] = Field(default_factory=list)
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    exit_code: int | None = None
