"""Lifecycle fields shared by persisted records and query projections."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from ..enums import TaskState, TaskType
from .source import TaskSource


class TaskStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: str
    run_id: str = Field(min_length=1)
    task_type: TaskType
    reg_name: str = ""
    source: TaskSource = Field(default_factory=TaskSource)
    report_kind: str | None = None
    state: TaskState = TaskState.QUEUED
    pid: int | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str = ""
    exit_code: int = Field(default=0, ge=0, le=255)
    log_path: str = ""
