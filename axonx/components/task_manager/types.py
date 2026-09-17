"""Public results returned by task managers."""

from typing import TypedDict


class TaskGraphNode(TypedDict):
    task_id: str
    kind: str
    task_name: str | None
    created_at: str | None
    parent_ids: list[str]
    missing: bool


class TaskGraphSummary(TaskGraphNode):
    root_id: str


class TaskGraphList(TypedDict):
    items: list[TaskGraphSummary]
    total: int
    offset: int
    limit: int


TaskGraphEdge = TypedDict("TaskGraphEdge", {"from": str, "to": str})


class TaskGraph(TypedDict):
    root_id: str
    selected_id: str
    nodes: list[TaskGraphNode]
    edges: list[TaskGraphEdge]


class TaskLogChunk(TypedDict):
    content: str
    start_offset: int
    next_offset: int
    file_size: int
    has_more_before: bool
    has_more_after: bool
    reset: bool
