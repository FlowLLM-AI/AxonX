"""Task catalog, graph, summary and context query models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import ConfigDict, Field

from .base import TaskModel
from .identity import TaskCategory, TaskState, TaskType
from .lifecycle import TaskMetadata, TaskStatus


class TaskInfo(TaskModel):
    """Describe an installed Task without generating parameter schemas."""

    model_config = ConfigDict(frozen=True)
    name: str
    source: Literal["native", "plugin"]
    plugin: str | None = None
    category: TaskCategory | None = None
    task_type: TaskType
    description: str


class TaskDefinition(TaskInfo):
    """An installed Task with its complete input and output schemas."""

    input_schema: dict[str, Any]
    output_schema: dict[str, Any]


class StepProgress(TaskModel):
    current: int
    total: int
    name: str
    percentage: float | None


class TaskSummary(TaskStatus):
    """Query projection only; never persisted beside the lifecycle record."""

    display_name: str
    is_online: bool
    is_replica: bool
    step_progress: StepProgress | None


class TaskGraphNode(TaskModel):
    task_id: str
    kind: TaskType
    task_name: str | None
    created_at: str | None
    parent_ids: list[str]
    state: TaskState | None
    missing: bool
    provisional: bool


class TaskGraphEdge(TaskModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
    from_: str = Field(alias="from")
    to: str


class TaskGraph(TaskModel):
    root_id: str
    selected_id: str
    nodes: list[TaskGraphNode]
    edges: list[TaskGraphEdge]


class TaskRelations(TaskModel):
    direct_upstream: list[str]
    ancestors: list[str]
    direct_downstream: list[str]
    missing: list[str]
    provisional: list[str]


class TaskContextSnapshot(TaskModel):
    """Read-only query data, distinct from the execution-owned TaskContext."""

    task_id: str
    status: TaskMetadata
    metadata_exists: bool
    metadata_path: str
    log_path: str | None
    graph: TaskGraph
    relations: TaskRelations
