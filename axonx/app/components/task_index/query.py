"""Snapshot queries: filtering, bounded summaries, lineage and Task context."""

from __future__ import annotations

from collections.abc import Iterator
from functools import cached_property

from ....task.models.identity import TaskState, TaskType, task_type_from_id, validate_upstream_task_ids
from ....task.models.lifecycle import TaskMetadata, TaskStatus
from ....task.models.query import (
    StepProgress,
    TaskContextSnapshot,
    TaskGraph,
    TaskGraphEdge,
    TaskGraphNode,
    TaskRelations,
    TaskSummary,
)
from ....task.storage.workspace import METADATA_FILE, task_directory


def task_sort_key(metadata: TaskMetadata) -> tuple[float, str]:
    """Order lifecycle records consistently by creation time and Task ID."""
    return (
        (metadata.created_at.timestamp() if metadata.created_at is not None else float("-inf")),
        metadata.task_id,
    )


def summarize_status(status: TaskMetadata) -> TaskSummary:
    """Keep list metadata and one progress summary, without copying task outputs."""
    summary = {name: getattr(status, name) for name in TaskStatus.model_fields}
    summary["error"] = status.error[:1000]
    summary["display_name"] = str(status.input_params.get("task_name") or status.reg_name)[:256]
    summary["is_replica"] = status.replica is not None
    summary["step_progress"] = None
    steps = [step for step in status.steps if step.parent is None]
    if steps:
        index = next(
            (i for i, step in enumerate(steps) if step.finished_at is None),
            len(steps) - 1,
        )
        step = steps[index]
        summary["step_progress"] = StepProgress(
            current=index + 1,
            total=len(steps),
            name=step.name[:256],
            percentage=step.percentage,
        )
    return TaskSummary(**summary)


_KIND_ORDER = {kind: index for index, kind in enumerate(TaskType)}


class TaskQuery:
    """Query one metadata snapshot; build lineage only when it is requested.

    Records are owned by the index and stay unchanged for this snapshot's lifetime.
    Public query results are isolated from the cached records and graph nodes.
    """

    def __init__(self, records: dict[str, TaskMetadata]) -> None:
        self.records = records

    def _matching(self, task_type: str | None, state: str | None) -> Iterator[TaskMetadata]:
        return (
            metadata
            for metadata in self.records.values()
            if (task_type is None or metadata.task_type == task_type) and (state is None or metadata.state == state)
        )

    def entries(self, *, task_type: str | None = None, state: str | None = None) -> dict[str, TaskMetadata]:
        """Return independent metadata records matching both filters."""
        return {metadata.task_id: metadata.model_copy(deep=True) for metadata in self._matching(task_type, state)}

    def summaries(self, *, task_type: str | None = None, state: str | None = None) -> list[TaskSummary]:
        """Return bounded summaries, newest first, without copying full outputs."""
        return [
            summarize_status(metadata)
            for metadata in sorted(self._matching(task_type, state), key=task_sort_key, reverse=True)
        ]

    @cached_property
    def _nodes(self) -> dict[str, TaskGraphNode]:
        nodes = {task_id: _node(task_id, entry) for task_id, entry in self.records.items()}
        for node in tuple(nodes.values()):
            for upstream_id in node.upstream_task_ids:
                if upstream_id not in nodes:
                    nodes[upstream_id] = _node(upstream_id, None)
        return nodes

    @cached_property
    def _downstream(self) -> dict[str, set[str]]:
        downstream: dict[str, set[str]] = {task_id: set() for task_id in self._nodes}
        for task_id, node in self._nodes.items():
            for upstream_id in node.upstream_task_ids:
                downstream[upstream_id].add(task_id)
        return downstream

    def _reachable(self, task_id: str, *, include_downstream: bool = False) -> set[str]:
        """Walk dependencies safely, including cycles and missing upstream nodes."""
        visited: set[str] = set()
        pending = [task_id]
        while pending:
            current = pending.pop()
            if current in visited:
                continue
            visited.add(current)
            pending.extend(self._nodes[current].upstream_task_ids)
            if include_downstream:
                pending.extend(self._downstream[current])
        return visited

    def graph(self, task_id: str) -> TaskGraph:
        """Return the connected component of an existing Task, including missing upstream Tasks."""
        if task_id not in self._nodes or self._nodes[task_id].missing:
            raise KeyError(task_id)
        members = [self._nodes[item] for item in self._reachable(task_id, include_downstream=True)]
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
        """Overlay fresh selected metadata while keeping other Tasks at the indexed snapshot."""
        task_id = status.task_id
        if self._nodes.get(task_id) != _node(task_id, status):
            return TaskQuery(self.records | {task_id: status}).context(status)
        graph = self.graph(task_id)
        return TaskContextSnapshot(
            task_id=task_id,
            status=status.model_copy(deep=True),
            metadata_path=f"{task_directory(task_id)}/{METADATA_FILE}",
            graph=graph,
            relations=TaskRelations(
                direct_upstream=sorted(self._nodes[task_id].upstream_task_ids),
                all_upstream=sorted(self._reachable(task_id) - {task_id}),
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
