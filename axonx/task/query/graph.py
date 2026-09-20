"""Draw Task dependency graphs from the records a workspace holds.

A graph is a property of the records, not of whatever happens to hold them: every
function here is a pure transformation of ``{task_id: TaskRecord}``, so it can be
reasoned about — and tested — without a workspace, a watcher or a lock.

A parent whose own record is gone stays in the graph as a placeholder: the branch
an earlier step belonged to is still the branch that produced this task, and hiding
it would present a lineage that never existed.
"""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, Field

from ..core.identity import task_type_from_id
from ..storage.workspace import KINDS, TaskRecord

KIND_ORDER = {kind: index for index, kind in enumerate(KINDS)}


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
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
    from_: str = Field(alias="from")
    to: str


class TaskGraph(BaseModel):
    root_id: str
    selected_id: str
    nodes: list[TaskGraphNode]
    edges: list[TaskGraphEdge]


def graph_summaries(
    records: Mapping[str, TaskRecord], query: str, offset: int, limit: int
) -> TaskGraphList:
    """Return one page of branch summaries, newest first.

    A branch is one connected component of the graph: a root task and everything
    derived from it. An empty query offers each branch by its root, which is the way
    into a pipeline, while a search offers the most recent task that matched.
    """
    nodes = _nodes(records)
    neighbors = _neighbors(nodes)
    query = query.strip().casefold()
    selected: list[TaskGraphSummary] = []
    seen: set[str] = set()
    for task_id in nodes:
        if task_id in seen:
            continue
        component = _component(neighbors, task_id)
        seen.update(component)
        matches = [nodes[item] for item in component if _matches(nodes[item], query)]
        if not matches:
            continue
        root_id = _root_id(nodes, component)
        representative = None if query else nodes.get(root_id)
        if representative is None or representative.missing:
            representative = max(matches, key=_recency)
        selected.append(
            TaskGraphSummary(**representative.model_dump(), root_id=root_id)
        )
    selected.sort(key=_recency, reverse=True)
    return TaskGraphList(
        items=selected[offset : offset + limit],
        total=len(selected),
        offset=offset,
        limit=limit,
    )


def task_graph(records: Mapping[str, TaskRecord], task_id: str) -> TaskGraph:
    """Return the graph containing one task; raise KeyError if it has no record."""
    if task_id not in records:
        raise KeyError(task_id)
    nodes = _nodes(records)
    component = _component(_neighbors(nodes), task_id)
    graph = [nodes[item] for item in component]
    return TaskGraph(
        root_id=_root_id(nodes, component),
        selected_id=task_id,
        nodes=sorted(
            graph,
            key=lambda node: (
                KIND_ORDER[node.kind],
                node.created_at or "",
                node.task_id,
            ),
        ),
        edges=sorted(
            (
                TaskGraphEdge(from_=parent, to=node.task_id)
                for node in graph
                for parent in node.parent_ids
            ),
            key=lambda edge: (edge.from_, edge.to),
        ),
    )


def _node(task_id: str, records: Mapping[str, TaskRecord]) -> TaskGraphNode:
    record = records.get(task_id)
    return TaskGraphNode(
        task_id=task_id,
        kind=task_type_from_id(task_id).value,
        task_name=record.reg_name if record else None,
        created_at=record.created_at if record else None,
        parent_ids=list(record.source_tasks) if record else [],
        missing=record is None,
    )


def _nodes(records: Mapping[str, TaskRecord]) -> dict[str, TaskGraphNode]:
    """Build graph nodes, adding placeholders for parents that have no record."""
    nodes = {task_id: _node(task_id, records) for task_id in records}
    for node in tuple(nodes.values()):
        for parent in node.parent_ids:
            if parent not in nodes:
                nodes[parent] = _node(parent, records)
    return nodes


def _neighbors(nodes: Mapping[str, TaskGraphNode]) -> dict[str, set[str]]:
    """Build the undirected adjacency of a graph, once per query."""
    neighbors = {task_id: set(node.parent_ids) for task_id, node in nodes.items()}
    for task_id, node in nodes.items():
        for parent in node.parent_ids:
            neighbors[parent].add(task_id)
    return neighbors


def _component(neighbors: Mapping[str, set[str]], task_id: str) -> set[str]:
    """Return every task connected to one task, upstream or downstream."""
    selected = {task_id}
    pending = [task_id]
    while pending:
        for neighbor in neighbors[pending.pop()] - selected:
            selected.add(neighbor)
            pending.append(neighbor)
    return selected


def _root_id(nodes: Mapping[str, TaskGraphNode], component: set[str]) -> str:
    """Return the earliest upstream task of a component, falling back to its earliest member."""
    members = [nodes[item] for item in component]
    roots = [node for node in members if not node.parent_ids] or members
    return min(roots, key=_recency).task_id


def _matches(node: TaskGraphNode, query: str) -> bool:
    """Whether an indexed node carries the query in its ID or its task name."""
    return not node.missing and (
        query in node.task_id.casefold() or query in (node.task_name or "").casefold()
    )


def _recency(node: TaskGraphNode) -> tuple[str, str]:
    """Order nodes by when they ran, falling back to their IDs for a stable tie-break."""
    return (node.created_at or "", node.task_id)
