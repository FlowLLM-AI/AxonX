"""Public task graph and log results."""

from pydantic import BaseModel, ConfigDict, Field


class TaskGraphNode(BaseModel):
    task_id: str
    kind: str
    task_name: str | None
    created_at: str | None
    parent_ids: list[str]
    missing: bool


class TaskGraphSummary(TaskGraphNode):
    root_id: str


class TaskGraphList(BaseModel):
    items: list[TaskGraphSummary]
    total: int
    offset: int
    limit: int


class TaskGraphEdge(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(alias="from")
    to: str


class TaskGraph(BaseModel):
    root_id: str
    selected_id: str
    nodes: list[TaskGraphNode]
    edges: list[TaskGraphEdge]


class TaskLogChunk(BaseModel):
    content: str
    start_offset: int
    next_offset: int
    file_size: int
    has_more_before: bool
    has_more_after: bool
    reset: bool
