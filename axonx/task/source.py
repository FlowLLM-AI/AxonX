"""Framework-owned provenance for one Task execution."""

from contextvars import ContextVar
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ScheduleTrigger(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: str = Field(min_length=1)
    job: str = Field(min_length=1)
    trigger_id: str = Field(min_length=1)
    triggered_at: datetime


class TaskSource(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["submit", "exec", "unknown"] = "unknown"
    schedule: ScheduleTrigger | None = None


TASK_SOURCE: ContextVar[TaskSource] = ContextVar("task_source", default=TaskSource(kind="submit"))
TASK_SOURCE_ENV = "AXONX_TASK_SOURCE"
