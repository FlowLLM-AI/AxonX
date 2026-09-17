"""Read task records and dependency graphs from the workspace."""

from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from watchfiles import awatch

from ....enums import TaskType
from ....schema import TaskStatus
from ....task.base import task_type_from_id
from ..types import TaskGraph, TaskGraphList

KINDS = tuple(kind.value for kind in TaskType)


@dataclass(frozen=True)
class TaskRecord:
    status: TaskStatus | None
    metadata: dict[str, Any] | None


class TaskIndex:
    """Keep an in-memory view of task directories current with workspace changes."""

    def __init__(self, workspace: Path, logger) -> None:
        self.root = workspace.expanduser().resolve()
        self.directories = tuple(self.root / kind for kind in KINDS)
        self.logger = logger
        self.records: dict[str, TaskRecord] = {}
        self.lock = asyncio.Lock()
        self.watcher: asyncio.Task | None = None

    async def start(self) -> None:
        for directory in self.directories:
            if directory.is_symlink():
                raise ValueError(f"Task directory cannot be a symlink: {directory}")
            directory.mkdir(parents=True, exist_ok=True)
        await self.reconcile()
        self.watcher = asyncio.create_task(self._watch(), name="axonx-task-index")

    async def close(self) -> None:
        if self.watcher is not None:
            self.watcher.cancel()
            with suppress(asyncio.CancelledError):
                await self.watcher
            self.watcher = None

    def path(self, task_id: str) -> Path:
        kind = task_type_from_id(task_id).value
        return self.root / kind / task_id

    def _read(self, task_id: str) -> TaskRecord | None:
        directory = self.path(task_id)
        if directory.parent.is_symlink() or directory.is_symlink() or not directory.is_dir():
            return None
        status = None
        status_path = directory / "status.json"
        if not status_path.is_symlink():
            try:
                status = TaskStatus.model_validate_json(status_path.read_text(encoding="utf-8"))
                if status.task_id != task_id or status.task_type != task_type_from_id(task_id):
                    status = None
            except (OSError, UnicodeError, ValueError):
                pass
        metadata = None
        metadata_path = directory / "metadata.json"
        if not metadata_path.is_symlink():
            try:
                value = json.loads(metadata_path.read_text(encoding="utf-8"))
                if isinstance(value, dict) and value.get("task_id") == task_id and value.get("task_type") == directory.parent.name:
                    metadata = value
            except (OSError, UnicodeError, ValueError):
                pass
        return TaskRecord(status, metadata)

    def _scan(self) -> dict[str, TaskRecord]:
        records = {}
        for parent in self.directories:
            if parent.is_symlink() or not parent.is_dir():
                continue
            for directory in parent.iterdir():
                if directory.is_symlink() or not directory.is_dir():
                    continue
                try:
                    if task_type_from_id(directory.name).value == parent.name:
                        record = self._read(directory.name)
                        if record is not None and (record.status is not None or record.metadata is not None):
                            records[directory.name] = record
                except ValueError:
                    continue
        return records

    async def reconcile(self) -> None:
        async with self.lock:
            self.records = await asyncio.to_thread(self._scan)

    async def refresh(self, task_id: str) -> None:
        async with self.lock:
            try:
                record = await asyncio.to_thread(self._read, task_id)
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
            self.records[status.task_id] = TaskRecord(status, current.metadata if current else None)

    async def remove(self, task_id: str) -> None:
        async with self.lock:
            self.records.pop(task_id, None)

    async def _watch(self) -> None:
        last_scan = 0.0
        while True:
            try:
                async for changes in awatch(*self.directories, debounce=200, rust_timeout=1000, yield_on_timeout=True):
                    affected = set()
                    for _, raw_path in changes:
                        try:
                            kind, task_id, *tail = Path(raw_path).relative_to(self.root).parts
                            if task_type_from_id(task_id).value == kind and (not tail or tail[0] in {"status.json", "metadata.json"}):
                                affected.add(task_id)
                        except ValueError:
                            continue
                    for task_id in affected:
                        await self.refresh(task_id)
                    now = asyncio.get_running_loop().time()
                    if now - last_scan >= 30:
                        await self.reconcile()
                        last_scan = now
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger.exception("Task watcher failed; retrying")
                await asyncio.sleep(1)
                try:
                    for directory in self.directories:
                        if not directory.is_symlink():
                            directory.mkdir(parents=True, exist_ok=True)
                    await self.reconcile()
                except Exception:
                    self.logger.exception("Task watcher recovery failed; retrying")

    @staticmethod
    def _node(task_id: str, records: dict[str, TaskRecord]) -> dict[str, Any]:
        record = records.get(task_id)
        metadata = record.metadata if record else None
        params = metadata.get("input_params") if metadata else None
        sources = params.get("source_tasks", []) if isinstance(params, dict) else []
        parents = []
        for source in sources if isinstance(sources, list) else []:
            try:
                task_type_from_id(source)
            except ValueError:
                continue
            if source not in parents:
                parents.append(source)
        return {
            "task_id": task_id,
            "kind": task_type_from_id(task_id).value,
            "task_name": metadata.get("reg_name") if metadata and isinstance(metadata.get("reg_name"), str) else None,
            "created_at": metadata.get("created_at") if metadata and isinstance(metadata.get("created_at"), str) else None,
            "parent_ids": parents,
            "missing": metadata is None,
        }

    @classmethod
    def _graph_nodes(cls, records: dict[str, TaskRecord]) -> dict[str, dict[str, Any]]:
        nodes = {task_id: cls._node(task_id, records) for task_id, record in records.items() if record.metadata is not None}
        for node in tuple(nodes.values()):
            for parent in node["parent_ids"]:
                nodes.setdefault(parent, cls._node(parent, records))
        return nodes

    @staticmethod
    def _component(nodes: dict[str, dict[str, Any]], task_id: str) -> set[str]:
        neighbors = {item: set(node["parent_ids"]) for item, node in nodes.items()}
        for item, node in nodes.items():
            for parent in node["parent_ids"]:
                neighbors[parent].add(item)
        selected = {task_id}
        pending = [task_id]
        while pending:
            for neighbor in neighbors[pending.pop()] - selected:
                selected.add(neighbor)
                pending.append(neighbor)
        return selected

    @staticmethod
    def _root_id(nodes: dict[str, dict[str, Any]], component: set[str]) -> str:
        return min((item for item in component if not nodes[item]["parent_ids"]), default=min(component))

    async def list_graphs(self, query: str, offset: int, limit: int) -> TaskGraphList:
        records = await self.snapshot()
        nodes = self._graph_nodes(records)
        query = query.strip().casefold()
        selected = []
        seen: set[str] = set()
        for task_id in nodes:
            if task_id in seen:
                continue
            component = self._component(nodes, task_id)
            seen.update(component)
            matches = [nodes[item] for item in component if not nodes[item]["missing"] and (query in item.casefold() or query in (nodes[item]["task_name"] or "").casefold())]
            if not matches:
                continue
            root_id = self._root_id(nodes, component)
            representative = max(matches, key=lambda item: (item["created_at"] or "", item["task_id"])) if query else nodes.get(root_id)
            if representative is None or nodes[root_id]["missing"]:
                representative = min(matches, key=lambda item: item["task_id"])
            selected.append({**representative, "root_id": root_id})
        selected.sort(key=lambda node: (node["created_at"] or "", node["task_id"]), reverse=True)
        return {"items": selected[offset:offset + limit], "total": len(selected), "offset": offset, "limit": limit}

    async def get_graph(self, task_id: str) -> TaskGraph:
        records = await self.snapshot()
        if task_id not in records or records[task_id].metadata is None:
            raise KeyError(task_id)
        nodes = self._graph_nodes(records)
        component = self._component(nodes, task_id)
        graph = [nodes[item] for item in component]
        return {
            "root_id": self._root_id(nodes, component),
            "selected_id": task_id,
            "nodes": sorted(graph, key=lambda node: (KINDS.index(node["kind"]), node["created_at"] or "", node["task_id"])),
            "edges": sorted(({"from": parent, "to": node["task_id"]} for node in graph for parent in node["parent_ids"]), key=lambda edge: (edge["from"], edge["to"])),
        }
