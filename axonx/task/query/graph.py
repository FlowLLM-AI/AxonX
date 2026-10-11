"""Build data-lineage graphs from the unified Task records."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..core.identity import parse_source_tasks, task_type_from_id
from ...enums import TaskState
from ..storage.workspace import KINDS, TaskMetadata

KIND_ORDER = {kind: index for index, kind in enumerate(KINDS)}


class TaskGraphNode(BaseModel):
    task_id: str
    kind: str
    task_name: str | None
    created_at: str | None
    parent_ids: list[str]
    state: str | None
    missing: bool
    provisional: bool


class TaskGraphEdge(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
    from_: str = Field(alias="from")
    to: str


class TaskGraph(BaseModel):
    root_id: str
    selected_id: str
    nodes: list[TaskGraphNode]
    edges: list[TaskGraphEdge]


def task_graph(entries: Mapping[str, TaskMetadata], task_id: str) -> TaskGraph:
    """Return the connected graph containing one lifecycle record."""
    if task_id not in entries:
        raise KeyError(task_id)
    nodes = _nodes(entries)
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
            (TaskGraphEdge(from_=parent, to=node.task_id) for node in graph for parent in node.parent_ids),
            key=lambda edge: (edge.from_, edge.to),
        ),
    )


def _status_sources(config: Mapping[str, Any] | None) -> list[str]:
    try:
        return parse_source_tasks(config.get("source_tasks", "") if config else "")
    except ValueError:
        return []


def _node(task_id: str, entries: Mapping[str, TaskMetadata]) -> TaskGraphNode:
    entry = entries.get(task_id)
    parents = _status_sources(entry.input_params if entry else None)
    parents = [parent for parent in parents if parent != task_id]
    return TaskGraphNode(
        task_id=task_id,
        kind=task_type_from_id(task_id).value,
        task_name=entry.reg_name if entry else None,
        created_at=entry.created_at.isoformat() if entry and entry.created_at else None,
        parent_ids=parents,
        state=entry.state.value if entry else None,
        missing=entry is None,
        provisional=entry is not None and entry.state != TaskState.SUCCEEDED,
    )


def _nodes(entries: Mapping[str, TaskMetadata]) -> dict[str, TaskGraphNode]:
    nodes = {task_id: _node(task_id, entries) for task_id in entries}
    for node in tuple(nodes.values()):
        for parent in node.parent_ids:
            if parent not in nodes:
                nodes[parent] = _node(parent, entries)
    return nodes


def _neighbors(nodes: Mapping[str, TaskGraphNode]) -> dict[str, set[str]]:
    neighbors = {task_id: set(node.parent_ids) for task_id, node in nodes.items()}
    for task_id, node in nodes.items():
        for parent in node.parent_ids:
            neighbors[parent].add(task_id)
    return neighbors


def _component(neighbors: Mapping[str, set[str]], task_id: str) -> set[str]:
    selected = {task_id}
    pending = [task_id]
    while pending:
        for neighbor in neighbors[pending.pop()] - selected:
            selected.add(neighbor)
            pending.append(neighbor)
    return selected


def _root_id(nodes: Mapping[str, TaskGraphNode], component: set[str]) -> str:
    members = [nodes[item] for item in component]
    roots = [node for node in members if not node.parent_ids] or members
    return min(roots, key=lambda node: (node.created_at or "", node.task_id)).task_id
