"""Live index of task artifact metadata and their dependency graph."""

import asyncio
import json
from contextlib import suppress
from pathlib import Path
from typing import Any

from watchfiles import awatch

from ..enums import ComponentEnum, TaskType
from ..task.base import task_type_from_id
from .base import BaseComponent
from .registry import R

KINDS = tuple(kind.value for kind in TaskType)


@R.register("local")
class TaskGraphIndex(BaseComponent):
    component_type = ComponentEnum.TASK_GRAPH

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._nodes: dict[str, dict[str, Any]] = {}
        self._children: dict[str, set[str]] = {}
        self._lock = asyncio.Lock()
        self._watcher: asyncio.Task | None = None

    async def _start(self):
        self._root = self.workspace_path.resolve()
        self._directories = [self._root / kind for kind in KINDS]
        for directory in self._directories:
            if directory.is_symlink():
                raise ValueError(f"Task directory cannot be a symlink: {directory}")
            directory.mkdir(parents=True, exist_ok=True)
        await self._reconcile()
        self._last_reconcile = 0.0
        self._watcher = asyncio.create_task(self._watch(), name="axonx-task-graph-index")

    async def _close(self):
        if self._watcher is not None:
            self._watcher.cancel()
            with suppress(asyncio.CancelledError):
                await self._watcher
            self._watcher = None

    def _read_node(self, path: Path) -> dict[str, Any] | None:
        task_id = path.parent.name
        kind = path.parent.parent.name
        if path.is_symlink() or path.parent.is_symlink() or path.parent.parent.is_symlink():
            return None
        try:
            if task_type_from_id(task_id).value != kind:
                return None
            metadata = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError):
            return None
        if not isinstance(metadata, dict) or metadata.get("task_id") != task_id or metadata.get("task_type") != kind:
            return None
        params = metadata.get("input_params")
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
            "kind": kind,
            "task_name": (metadata.get("reg_name") if isinstance(metadata.get("reg_name"), str) else kind),
            "created_at": (metadata.get("created_at") if isinstance(metadata.get("created_at"), str) else None),
            "parent_ids": parents,
            "missing": False,
        }

    def _scan(self) -> dict[str, dict[str, Any]]:
        nodes = {}
        for directory in self._directories:
            if not directory.is_dir() or directory.is_symlink():
                continue
            for task_dir in directory.iterdir():
                if task_dir.is_dir() and not task_dir.is_symlink():
                    node = self._read_node(task_dir / "metadata.json")
                    if node is not None:
                        nodes[node["task_id"]] = node
        return nodes

    async def _reconcile(self):
        nodes = await asyncio.to_thread(self._scan)
        async with self._lock:
            self._nodes = nodes
            self._children = {}
            for node in nodes.values():
                for parent in node["parent_ids"]:
                    self._children.setdefault(parent, set()).add(node["task_id"])

    async def _update(self, task_id: str, kind: str):
        node = await asyncio.to_thread(self._read_node, self._root / kind / task_id / "metadata.json")
        async with self._lock:
            old = self._nodes.pop(task_id, None)
            if old is not None:
                for parent in old["parent_ids"]:
                    children = self._children[parent]
                    children.discard(task_id)
                    if not children:
                        del self._children[parent]
            if node is not None:
                self._nodes[task_id] = node
                for parent in node["parent_ids"]:
                    self._children.setdefault(parent, set()).add(task_id)

    async def _watch(self):
        while True:
            try:
                async for changes in awatch(*self._directories, debounce=200, rust_timeout=1000, yield_on_timeout=True):
                    affected = set()
                    for _, raw_path in changes:
                        path = Path(raw_path)
                        try:
                            kind, task_id, *rest = path.relative_to(self._root).parts
                        except ValueError:
                            continue
                        if kind in KINDS and (not rest or rest == ["metadata.json"]):
                            affected.add((task_id, kind))
                    for task_id, kind in affected:
                        await self._update(task_id, kind)
                    # A missed notification or recreated watched directory is repaired here.
                    if asyncio.get_running_loop().time() - self._last_reconcile >= 30:
                        await self._reconcile()
                        self._last_reconcile = asyncio.get_running_loop().time()
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger.exception("Task graph watcher failed; retrying")
                await asyncio.sleep(1)
                for directory in self._directories:
                    if directory.is_symlink():
                        continue
                    directory.mkdir(parents=True, exist_ok=True)
                await self._reconcile()

    def _node(self, task_id: str) -> dict[str, Any]:
        node = self._nodes.get(task_id)
        if node is not None:
            return node
        return {
            "task_id": task_id,
            "kind": task_type_from_id(task_id).value,
            "task_name": None,
            "created_at": None,
            "parent_ids": [],
            "missing": True,
        }

    def _component(self, task_id: str) -> set[str]:
        selected = {task_id}
        pending = [task_id]
        while pending:
            current = pending.pop()
            for neighbor in (
                *self._node(current)["parent_ids"],
                *self._children.get(current, ()),
            ):
                if neighbor not in selected:
                    selected.add(neighbor)
                    pending.append(neighbor)
        return selected

    def _root_id(self, component: set[str]) -> str:
        return min(
            (item for item in component if not self._node(item)["parent_ids"]),
            default=min(component),
        )

    async def list_graphs(self, query: str = "", offset: int = 0, limit: int = 50) -> dict[str, Any]:
        async with self._lock:
            query = query.strip().casefold()
            items = []
            seen: set[str] = set()
            for task_id in self._nodes:
                if task_id in seen:
                    continue
                component = self._component(task_id)
                seen.update(component)
                matches = [
                    self._nodes[item]
                    for item in component
                    if item in self._nodes
                    and (query in item.casefold() or query in self._nodes[item]["task_name"].casefold())
                ]
                if not matches:
                    continue
                root_id = self._root_id(component)
                representative = (
                    max(
                        matches,
                        key=lambda item: (item["created_at"] or "", item["task_id"]),
                    )
                    if query
                    else self._nodes.get(root_id, min(matches, key=lambda item: item["task_id"]))
                )
                items.append({**representative, "root_id": root_id})
            items.sort(
                key=lambda node: (node["created_at"] or "", node["task_id"]),
                reverse=True,
            )
            return {
                "items": items[offset : offset + limit],
                "total": len(items),
                "offset": offset,
                "limit": limit,
            }

    async def get_graph(self, task_id: str) -> dict[str, Any]:
        async with self._lock:
            if task_id not in self._nodes:
                raise ValueError(f"Task artifact not found: {task_id}")
            component = self._component(task_id)
            nodes = [self._node(item) for item in component]
            return {
                "root_id": self._root_id(component),
                "selected_id": task_id,
                "nodes": sorted(
                    nodes,
                    key=lambda node: (
                        KINDS.index(node["kind"]),
                        node["created_at"] or "",
                        node["task_id"],
                    ),
                ),
                "edges": sorted(
                    ({"from": parent, "to": node["task_id"]} for node in nodes for parent in node["parent_ids"]),
                    key=lambda edge: (edge["from"], edge["to"]),
                ),
            }
