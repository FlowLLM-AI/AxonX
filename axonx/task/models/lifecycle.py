"""Invocation context, child results, lifecycle, progress and display-replica records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import AwareDatetime, ConfigDict, Field

from .artifacts import Protocol
from .base import TaskModel
from .identity import TaskState, TaskType
from .params import BaseOutputParams


class TaskStepStatus(TaskModel):
    """One step snapshot, shared by persistence and progress events."""

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


class ReplicaFile(TaskModel):
    size: int = Field(ge=0)
    revision: str = Field(min_length=1)
    sampled: bool = False
    rows: int | None = Field(default=None, ge=0)
    source_rows: int | None = Field(default=None, ge=0)
    dates: list[str] = Field(default_factory=list)


class LiveSnapshot(TaskModel):
    """One ordered, read-only snapshot of a parent Task and its children."""

    source_id: str = Field(min_length=1)
    root_task_id: str = Field(min_length=1)
    root_started_at: AwareDatetime
    captured_at: AwareDatetime
    revision: int = Field(gt=0)


class ReplicaLog(TaskModel):
    path: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)


class DisplayReplica(TaskModel):
    purpose: Literal["display"] = "display"
    source_revision: str = Field(min_length=1)
    policy_revision: str = Field(min_length=1)
    files: dict[str, ReplicaFile]
    omitted: dict[str, str] = Field(default_factory=dict)
    source_log_path: str = ""
    snapshot: LiveSnapshot | None = None
    log: ReplicaLog | None = None


@dataclass(frozen=True)
class TaskContext:
    """Immutable invocation identity shared with the executor and child Tasks."""

    workspace_path: Path
    registration_name: str
    task_id: str
    created_at: datetime
    timezone: str
    parent_task_id: str | None = None  # Calling Task, independent of input dependencies.
    execution_target: str | None = None


class TaskStatus(TaskModel):
    task_id: str
    task_type: TaskType
    reg_name: str = ""
    parent_task_id: str | None = Field(default=None, description="Task that directly invoked this Task.")
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


class ChildTaskRecord(TaskModel):
    """Snapshot of one child invocation; invalid inputs may have no Task ID."""

    node_name: str
    attempt: int = Field(ge=1)
    reg_name: str = Field(description="Registered name passed to run_task.")
    child_task_id: str | None = Field(default=None, description="Invoked Task ID, absent if construction failed.")
    started_at: AwareDatetime | None = None
    state: TaskState = TaskState.RUNNING
    exit_code: int = Field(default=0, ge=0, le=255)
    error: str = ""


@dataclass(frozen=True)
class ChildTaskResult:
    """An invocation snapshot plus its typed output, when output was built."""

    record: ChildTaskRecord
    output_params: BaseOutputParams | None = None

    @property
    def child_task_id(self) -> str:
        if self.record.child_task_id is None:
            raise RuntimeError("Child Task was not constructed")
        return self.record.child_task_id

    @property
    def success(self) -> bool:
        return self.record.state == TaskState.SUCCEEDED

    @property
    def output(self) -> dict:
        if self.output_params is None:
            raise RuntimeError("Child Task output is unavailable")
        return self.output_params.model_dump(mode="json", by_alias=True)


class TaskMetadata(Protocol, TaskStatus):
    """The complete current lifecycle record, from running to terminal."""

    model_config = ConfigDict(extra="forbid")
    input_params: dict[str, Any] = Field(default_factory=dict)
    output_params: dict[str, Any] = Field(default_factory=dict)
    children: list[ChildTaskRecord] = Field(
        default_factory=list, description="Direct child invocation records, independent of input dependencies."
    )
    steps: list[TaskStepStatus] = Field(default_factory=list)
    replica: DisplayReplica | None = None

    def current_children(self) -> list[ChildTaskRecord]:
        """Return the latest invocation per child ID; retain all attempts in metadata."""
        return list({child.child_task_id: child for child in self.children if child.child_task_id}.values())
