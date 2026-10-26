"""Query Task lineage and context from one metadata snapshot."""

from __future__ import annotations

from collections.abc import Collection, Mapping

from ....task.models.identity import TaskState, TaskType, task_type_from_id, validate_upstream_task_ids
from ....task.models.lifecycle import TaskMetadata
from ....task.models.query import TaskContextSnapshot, TaskGraph, TaskGraphEdge, TaskGraphNode, TaskRelations
from ....task.storage.workspace import METADATA_FILE, task_directory

_KIND_ORDER = {kind: index for index, kind in enumerate(TaskType)}


class TaskGraphQuery:
    """Share lineage nodes and adjacency indexes across graph and context queries."""

    def __init__(self, entries: Mapping[str, TaskMetadata]) -> None:
        self._nodes = {task_id: _node(task_id, entry) for task_id, entry in entries.items()}
        for node in tuple(self._nodes.values()):
            for upstream_id in node.upstream_task_ids:
                if upstream_id not in self._nodes:
                    self._nodes[upstream_id] = _node(upstream_id, None)
        self._upstream = {task_id: node.upstream_task_ids for task_id, node in self._nodes.items()}
        self._downstream: dict[str, set[str]] = {task_id: set() for task_id in self._nodes}
        for task_id, upstream_ids in self._upstream.items():
            for upstream_id in upstream_ids:
                self._downstream[upstream_id].add(task_id)

    def graph(self, task_id: str) -> TaskGraph:
        """Return the connected component of an existing Task, including missing upstream Tasks."""
        if task_id not in self._nodes or self._nodes[task_id].missing:
            raise KeyError(task_id)
        members = [self._nodes[item] for item in _reachable(task_id, self._upstream, self._downstream)]
        roots = [node for node in members if not node.upstream_task_ids] or members
        return TaskGraph(
            root_id=min(roots, key=lambda node: (node.created_at or "", node.task_id)).task_id,
            selected_id=task_id,
            nodes=sorted(
                (node.model_copy(deep=True) for node in members),
                key=lambda node: (_KIND_ORDER[node.kind], node.created_at or "", node.task_id),
            ),
            edges=sorted(
                (
                    TaskGraphEdge(from_=upstream_id, to=node.task_id)
                    for node in members
                    for upstream_id in node.upstream_task_ids
                ),
                key=lambda edge: (edge.from_, edge.to),
            ),
        )

    def context(self, status: TaskMetadata) -> TaskContextSnapshot:
        """Combine fresh status with the indexed graph and its upstream relationships."""
        task_id = status.task_id
        graph = self.graph(task_id)
        return TaskContextSnapshot(
            task_id=task_id,
            status=status,
            metadata_path=f"{task_directory(task_id)}/{METADATA_FILE}",
            graph=graph,
            relations=TaskRelations(
                direct_upstream=sorted(self._upstream[task_id]),
                all_upstream=sorted(_reachable(task_id, self._upstream) - {task_id}),
                direct_downstream=sorted(self._downstream[task_id]),
                missing=sorted(node.task_id for node in graph.nodes if node.missing),
                provisional=sorted(node.task_id for node in graph.nodes if node.provisional),
            ),
        )


def _node(task_id: str, entry: TaskMetadata | None) -> TaskGraphNode:
    try:
        upstream_ids = validate_upstream_task_ids(entry.input_params.get("upstream_task_ids", []) if entry else [])
    except ValueError:
        upstream_ids = []
    return TaskGraphNode(
        task_id=task_id,
        kind=task_type_from_id(task_id),
        task_name=entry.reg_name if entry else None,
        created_at=entry.created_at.isoformat() if entry and entry.created_at else None,
        upstream_task_ids=[upstream_id for upstream_id in upstream_ids if upstream_id != task_id],
        state=entry.state if entry else None,
        missing=entry is None,
        provisional=entry is not None and entry.state != TaskState.SUCCEEDED,
    )


def _reachable(task_id: str, *relations: Mapping[str, Collection[str]]) -> set[str]:
    """Walk any combination of directed relationships, including cycles and missing nodes."""
    visited: set[str] = set()
    pending = [task_id]
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        for links in relations:
            pending.extend(links.get(current, ()))
    return visited
