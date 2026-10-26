"""Task lifecycle, step progress, and display-replica records."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from ..task_enums import TaskCategory, TaskState, TaskType
from .artifacts import Protocol


class TaskStepStatus(BaseModel):
    """One step snapshot, shared by persistence and progress events."""

    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)
    label: str = ""
    parent: str | None = None
    percentage: float | None = Field(default=None, ge=0, le=100)
    group: str = ""
    state: Literal["pending", "waiting", "running", "done", "failed", "missed", "skipped"] = "pending"
    phase: str = ""
    completed: int | None = Field(default=None, ge=0)
    total: int | None = Field(default=None, ge=0)
    unit: str = ""
    scheduled_at: AwareDatetime | None = None
    deadline: AwareDatetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    files: dict[str, str] = Field(default_factory=dict)
    error: str = ""


class ReplicaFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    size: int = Field(ge=0)
    revision: str = Field(min_length=1)
    sampled: bool = False
    rows: int | None = Field(default=None, ge=0)
    source_rows: int | None = Field(default=None, ge=0)
    dates: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def read_legacy(cls, value):
        if isinstance(value, dict) and "sha256" in value:
            value = dict(value)
            value.setdefault("revision", "legacy:" + value.pop("sha256"))
        return value


class LiveSnapshot(BaseModel):
    """One ordered, read-only snapshot of a parent Task and its children."""

    model_config = ConfigDict(extra="forbid")
    source_id: str = Field(min_length=1)
    root_task_id: str = Field(min_length=1)
    root_started_at: AwareDatetime
    captured_at: AwareDatetime
    revision: int = Field(gt=0)


class ReplicaLog(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)


class DisplayReplica(BaseModel):
    model_config = ConfigDict(extra="forbid")
    purpose: Literal["display"] = "display"
    source_revision: str = Field(min_length=1)
    policy_revision: str = Field(min_length=1)
    files: dict[str, ReplicaFile]
    omitted: dict[str, str] = Field(default_factory=dict)
    source_log_path: str = ""
    snapshot: LiveSnapshot | None = None
    log: ReplicaLog | None = None

    @model_validator(mode="before")
    @classmethod
    def read_legacy(cls, value):
        if isinstance(value, dict):
            value = dict(value)
            for old, new in (
                ("source_digest", "source_revision"),
                ("policy_digest", "policy_revision"),
            ):
                if old in value:
                    value.setdefault(new, "legacy:" + value.pop(old))
        return value


class TaskSource(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["exec", "unknown"] = "unknown"


class TaskStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: str
    task_type: TaskType
    reg_name: str = ""
    source: TaskSource = Field(default_factory=TaskSource)
    parent_task_id: str | None = None
    category: TaskCategory | None = None
    report_kind: str | None = None
    state: TaskState = TaskState.RUNNING
    pid: int = Field(gt=0)
    machine_id: str = Field(min_length=1)
    execution_target: str | None = None
    workspace_dir: str | None = None
    process_started_at: AwareDatetime
    created_at: datetime | None = None
    started_at: AwareDatetime
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
    started_at: AwareDatetime | None = None
    state: TaskState = TaskState.RUNNING
    exit_code: int = Field(default=0, ge=0, le=255)
    error: str = ""


class TaskMetadata(Protocol, TaskStatus):
    """The complete current lifecycle record, from running to terminal."""

    model_config = ConfigDict(extra="forbid")
    input_params: dict[str, Any] = Field(default_factory=dict)
    output_params: dict[str, Any] = Field(default_factory=dict)
    children: list[ChildTaskRecord] = Field(default_factory=list)
    steps: list[TaskStepStatus] = Field(default_factory=list)
    replica: DisplayReplica | None = None


def current_children(status: TaskMetadata):
    """Named directories contain the latest invocation; earlier attempts stay in metadata."""
    return {child.task_id: child for child in status.children if child.task_id}.values()
