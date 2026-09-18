"""Read task records and dependency graphs from the workspace."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Container
from contextlib import suppress
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

from watchfiles import awatch

from ....enums import TaskType
from ....schema import (
    TaskGraph,
    TaskGraphEdge,
    TaskGraphList,
    TaskGraphNode,
    TaskGraphSummary,
    TaskStatus,
)
from ....task.identity import task_type_from_id

KINDS = tuple(kind.value for kind in TaskType)
KIND_ORDER = {kind: index for index, kind in enumerate(KINDS)}
WATCH_FILES = frozenset({"status.json", "metadata.json"})


@dataclass(frozen=True)
class WatchOptions:
    """Tuning for the workspace file watcher."""

    recursive: bool = True
    force_polling: bool = True
    debounce: int = 60_000
    step: int = 3_000
    poll_delay_ms: int = 3_000

    @classmethod
    def collect(cls, values: dict[str, Any]) -> WatchOptions:
        """Consume watch settings from a component configuration mapping."""
        known = {field.name for field in fields(cls)}
        return cls(**{key: values.pop(key) for key in tuple(values) if key in known})

    def as_awatch_kwargs(self) -> dict[str, Any]:
        """Return the keyword arguments accepted by ``watchfiles.awatch``."""
        return {field.name: getattr(self, field.name) for field in fields(self)}


@dataclass(frozen=True)
class TaskRecord:
    status: TaskStatus | None
    metadata: dict[str, Any] | None


def _text(metadata: dict[str, Any] | None, key: str) -> str | None:
    """Read one string field from optional task metadata."""
    value = metadata.get(key) if metadata else None
    return value if isinstance(value, str) else None


class TaskIndex:
    """Keep an in-memory view of task directories current with workspace changes."""

    def __init__(self, workspace: Path, logger, watch: WatchOptions | None = None) -> None:
        self.root = workspace.expanduser().resolve()
        self.directories = tuple(self.root / kind for kind in KINDS)
        self.logger = logger
        self.watch = watch or WatchOptions()
        self.records: dict[str, TaskRecord] = {}
        self.lock = asyncio.Lock()
        self.watcher: asyncio.Task | None = None

    async def start(self) -> None:
        self._ensure_directories()
        await self.reconcile()
        self.watcher = asyncio.create_task(self._watch(), name="axonx-task-index")

    async def close(self) -> None:
        if self.watcher is not None:
            self.watcher.cancel()
            with suppress(asyncio.CancelledError):
                await self.watcher
            self.watcher = None

    def _ensure_directories(self) -> None:
        for directory in self.directories:
            if directory.is_symlink():
                raise ValueError(f"Task directory cannot be a symlink: {directory}")
            directory.mkdir(parents=True, exist_ok=True)

    def path(self, task_id: str) -> Path:
        kind = task_type_from_id(task_id).value
        return self.root / kind / task_id

    def _parts(self, raw_path: str) -> tuple[str, str, str] | None:
        """Split a watched path into its kind, task ID and file name."""
        try:
            kind, task_id, filename = Path(raw_path).relative_to(self.root).parts
            if filename not in WATCH_FILES or task_type_from_id(task_id).value != kind:
                return None
        except ValueError:
            return None
        return kind, task_id, filename

    def _watch_file(self, _change, raw_path: str) -> bool:
        return self._parts(raw_path) is not None

    @staticmethod
    def _read_status(task_id: str, directory: Path) -> TaskStatus | None:
        path = directory / "status.json"
        if path.is_symlink():
            return None
        try:
            status = TaskStatus.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError):
            return None
        return status if status.task_id == task_id and status.task_type == task_type_from_id(task_id) else None

    @staticmethod
    def _read_metadata(task_id: str, directory: Path) -> dict[str, Any] | None:
        path = directory / "metadata.json"
        if path.is_symlink():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError):
            return None
        if isinstance(value, dict) and value.get("task_id") == task_id and value.get("task_type") == directory.parent.name:
            return value
        return None

    def _read(
        self, task_id: str, changed: Container[str] = WATCH_FILES, previous: TaskRecord | None = None,
    ) -> TaskRecord | None:
        """Read one task directory, reusing the parts that did not change on disk."""
        directory = self.path(task_id)
        if directory.parent.is_symlink() or directory.is_symlink() or not directory.is_dir():
            return None
        status = previous.status if previous and "status.json" not in changed else self._read_status(task_id, directory)
        metadata = previous.metadata if previous and "metadata.json" not in changed else self._read_metadata(task_id, directory)
        return TaskRecord(status, metadata)

    @staticmethod
    def _is_task_directory(directory: Path, kind: str) -> bool:
        """Whether a directory name is a task ID belonging to the given kind."""
        try:
            return task_type_from_id(directory.name).value == kind
        except ValueError:
            return False

    def _scan(self) -> dict[str, TaskRecord]:
        records = {}
        for parent in self.directories:
            if parent.is_symlink() or not parent.is_dir():
                continue
            for directory in parent.iterdir():
                if directory.is_symlink() or not directory.is_dir() or not self._is_task_directory(directory, parent.name):
                    continue
                record = self._read(directory.name)
                if record is not None and (record.status is not None or record.metadata is not None):
                    records[directory.name] = record
        return records

    async def reconcile(self) -> None:
        async with self.lock:
            self.records = await asyncio.to_thread(self._scan)

    async def refresh(self, task_id: str, changed: Container[str] = WATCH_FILES) -> None:
        """Re-read one task, keeping the parts of its record that did not change."""
        async with self.lock:
            previous = self.records.get(task_id)
            try:
                record = await asyncio.to_thread(self._read, task_id, changed, previous)
            except ValueError:
                record = None
            if record is None or (record.status is None and record.metadata is None):
                self.records.pop(task_id, None)
            else:
                self.records[task_id] = record

    async def snapshot(self) -> dict[str, TaskRecord]:
        async with self.lock:
            return dict(self.records)

    async def get(self, task_id: str) -> TaskRecord:
        async with self.lock:
            return self.records[task_id]

    async def put_status(self, status: TaskStatus) -> None:
        async with self.lock:
            current = self.records.get(status.task_id)
            # The status file is rewritten far more often than metadata, which is written once per task.
            self.records[status.task_id] = TaskRecord(status, current.metadata if current else None)

    async def remove(self, task_id: str) -> None:
        async with self.lock:
            self.records.pop(task_id, None)

    async def _watch(self) -> None:
        while True:
            try:
                async for changes in awatch(
                    *self.directories, watch_filter=self._watch_file, **self.watch.as_awatch_kwargs(),
                ):
                    for task_id, changed in self._changed_tasks(changes).items():
                        await self.refresh(task_id, changed)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger.exception("Task watcher failed; retrying")
                await asyncio.sleep(1)
                await asyncio.to_thread(self._ensure_directories)

    def _changed_tasks(self, changes) -> dict[str, set[str]]:
        """Group watcher changes into task IDs and the file names that changed."""
        touched: dict[str, set[str]] = {}
        for _, raw_path in changes:
            parts = self._parts(raw_path)
            if parts is not None:
                touched.setdefault(parts[1], set()).add(parts[2])
        return touched

    @staticmethod
    def _node(task_id: str, records: dict[str, TaskRecord]) -> TaskGraphNode:
        record = records.get(task_id)
        metadata = record.metadata if record else None
        params = metadata.get("input_params") if metadata else None
        sources = params.get("source_tasks", []) if isinstance(params, dict) else []
        parents: list[str] = []
        for source in sources if isinstance(sources, list) else []:
            try:
                task_type_from_id(source)
            except ValueError:
                continue
            if source not in parents:
                parents.append(source)
        return TaskGraphNode(
            task_id=task_id,
            kind=task_type_from_id(task_id).value,
            task_name=_text(metadata, "reg_name"),
            created_at=_text(metadata, "created_at"),
            parent_ids=parents,
            missing=metadata is None,
        )

    def _graph_nodes(self, records: dict[str, TaskRecord]) -> dict[str, TaskGraphNode]:
        """Build graph nodes, adding placeholders for parents that have no record."""
        nodes = {
            task_id: self._node(task_id, records)
            for task_id, record in records.items()
            if record.metadata is not None
        }
        for node in tuple(nodes.values()):
            for parent in node.parent_ids:
                if parent not in nodes:
                    nodes[parent] = self._node(parent, records)
        return nodes

    @staticmethod
    def _neighbors(nodes: dict[str, TaskGraphNode]) -> dict[str, set[str]]:
        """Build the undirected adjacency of a graph, built once per query."""
        neighbors = {task_id: set(node.parent_ids) for task_id, node in nodes.items()}
        for task_id, node in nodes.items():
            for parent in node.parent_ids:
                neighbors[parent].add(task_id)
        return neighbors

    @staticmethod
    def _component(neighbors: dict[str, set[str]], task_id: str) -> set[str]:
        """Return every task connected to one task, upstream or downstream."""
        selected = {task_id}
        pending = [task_id]
        while pending:
            for neighbor in neighbors[pending.pop()] - selected:
                selected.add(neighbor)
                pending.append(neighbor)
        return selected

    @staticmethod
    def _recency(node: TaskGraphNode) -> tuple[str, str]:
        return (node.created_at or "", node.task_id)

    @staticmethod
    def _root_id(nodes: dict[str, TaskGraphNode], component: set[str]) -> str:
        """Return the earliest upstream task of a component, falling back to its earliest member."""
        members = [nodes[item] for item in component]
        roots = [node for node in members if not node.parent_ids] or members
        return min(roots, key=TaskIndex._recency).task_id

    @staticmethod
    def _matches(node: TaskGraphNode, query: str) -> bool:
        """Whether an indexed node carries the query in its ID or its task name."""
        return not node.missing and (query in node.task_id.casefold() or query in (node.task_name or "").casefold())

    async def list_graphs(self, query: str, offset: int, limit: int) -> TaskGraphList:
        records = await self.snapshot()
        nodes = self._graph_nodes(records)
        neighbors = self._neighbors(nodes)
        query = query.strip().casefold()
        selected: list[TaskGraphSummary] = []
        seen: set[str] = set()
        for task_id in nodes:
            if task_id in seen:
                continue
            component = self._component(neighbors, task_id)
            seen.update(component)
            matches = [nodes[item] for item in component if self._matches(nodes[item], query)]
            if not matches:
                continue
            root_id = self._root_id(nodes, component)
            # An empty query lists the branch root; a search lists the most recent hit.
            representative = None if query else nodes.get(root_id)
            if representative is None or representative.missing:
                representative = max(matches, key=self._recency)
            selected.append(TaskGraphSummary(**representative.model_dump(), root_id=root_id))
        selected.sort(key=self._recency, reverse=True)
        return TaskGraphList(items=selected[offset:offset + limit], total=len(selected), offset=offset, limit=limit)

    async def get_graph(self, task_id: str) -> TaskGraph:
        records = await self.snapshot()
        if task_id not in records or records[task_id].metadata is None:
            raise KeyError(task_id)
        nodes = self._graph_nodes(records)
        component = self._component(self._neighbors(nodes), task_id)
        graph = [nodes[item] for item in component]
        return TaskGraph(
            root_id=self._root_id(nodes, component),
            selected_id=task_id,
            nodes=sorted(graph, key=lambda node: (KIND_ORDER[node.kind], node.created_at or "", node.task_id)),
            edges=sorted((TaskGraphEdge(from_=parent, to=node.task_id) for node in graph for parent in node.parent_ids),
                         key=lambda edge: (edge.from_, edge.to)),
        )