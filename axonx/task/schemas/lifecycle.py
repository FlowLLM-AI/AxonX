"""Sources, invocation snapshots, and persisted Task lifecycle records."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ...enums import TaskCategory, TaskState, TaskType
from ...progress import TaskStepStatus
from .protocol import Protocol
from .replica import DisplayReplica


class ScheduleTrigger(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: str = Field(min_length=1)
    job: str = Field(min_length=1)
    trigger_id: str = Field(min_length=1)
    triggered_at: datetime
    scheduler_id: str | None = None


class TaskSource(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["submit", "exec", "unknown"] = "unknown"
    schedule: ScheduleTrigger | None = None


class TaskStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: str
    run_id: str = Field(min_length=1)
    task_type: TaskType
    reg_name: str = ""
    source: TaskSource = Field(default_factory=TaskSource)
    parent_run_id: str | None = None
    category: TaskCategory | None = None
    report_kind: str | None = None
    state: TaskState = TaskState.QUEUED
    pid: int | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str = ""
    exit_code: int = Field(default=0, ge=0, le=255)
    log_path: str = ""


class ChildTaskRecord(BaseModel):
    """Snapshot of one child invocation; invalid inputs may have no Task ID."""

    model_config = ConfigDict(extra="forbid")
    node_name: str
    attempt: int = Field(ge=1)
    task: str
    task_id: str | None = None
    run_id: str
    state: TaskState = TaskState.QUEUED
    exit_code: int = Field(default=0, ge=0, le=255)
    error: str = ""


class TaskMetadata(Protocol, TaskStatus):
    """The complete current lifecycle record, from queued to terminal."""

    model_config = ConfigDict(extra="forbid")
    input_params: dict[str, Any] = Field(default_factory=dict)
    output_params: dict[str, Any] = Field(default_factory=dict)
    children: list[ChildTaskRecord] = Field(default_factory=list)
    steps: list[TaskStepStatus] = Field(default_factory=list)
    replica: DisplayReplica | None = None


@dataclass(frozen=True, slots=True)
class TaskHandle:
    task_id: str
    run_id: str
    task: str


def current_children(status: TaskMetadata):
    """Named directories contain the latest invocation; earlier attempts stay in metadata."""
    return {child.task_id: child for child in status.children if child.task_id}.values()
