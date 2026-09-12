"""Durable task status and progress models."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from ..enumeration import TaskState, TaskType


class TaskStepStatus(BaseModel):
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
    steps: list[TaskStepStatus] = Field(default_factory=list)
    result: dict[str, Any] = Field(default_factory=dict)
    error: str = Field(default="", min_length=0)
    exit_code: int = Field(default=0, ge=0, le=255)
    log_path: str = Field(default="", min_length=0)
