"""Index task artifacts and build their dependency graphs."""

import json
from pathlib import Path
from typing import Any

from ...enums import TaskType
from ...task.base import task_type_from_id

KINDS = tuple(task_type.value for task_type in TaskType)


def _task_index(root: Path) -> dict[str, dict[str, Any]]:
    nodes: dict[str, dict[str, Any]] = {}
    for kind in KINDS:
        directory = root / kind
        if not directory.is_dir():
            continue
        for task_dir in directory.iterdir():
            if not task_dir.is_dir() or task_dir.is_symlink():
                continue
            metadata_path = task_dir / "metadata.json"
            try:
                if metadata_path.is_symlink():
                    continue
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, ValueError):
                continue
            if not isinstance(metadata, dict):
                continue
            task_id = task_dir.name
            try:
                if task_type_from_id(task_id).value != kind:
                    continue
            except ValueError:
                continue
            if metadata.get("task_id") != task_id or metadata.get("task_type") != kind:
                continue
            input_params = metadata.get("input_params")
            sources = input_params.get("source_tasks", []) if isinstance(input_params, dict) else []
            if not isinstance(sources, list):
                sources = []
            parent_ids = []
            for source in sources:
                try:
                    task_type_from_id(source)
                except ValueError:
                    continue
                if source not in parent_ids:
                    parent_ids.append(source)
            nodes[task_id] = {
                "task_id": task_id,
                "kind": kind,
                "task_name": metadata.get("reg_name") if isinstance(metadata.get("reg_name"), str) else kind,
                "created_at": metadata.get("created_at") if isinstance(metadata.get("created_at"), str) else None,
                "parent_ids": parent_ids,
                "missing": False,
            }
    for node in tuple(nodes.values()):
        for parent_id in node["parent_ids"]:
            if parent_id not in nodes:
                nodes[parent_id] = {
                    "task_id": parent_id,
                    "kind": task_type_from_id(parent_id).value,
                    "task_name": None,
                    "created_at": None,
                    "parent_ids": [],
                    "missing": True,
                }
    return nodes


def _component(nodes: dict[str, dict[str, Any]], task_id: str) -> set[str]:
    neighbors = {node_id: set(node["parent_ids"]) for node_id, node in nodes.items()}
    for node_id, node in nodes.items():
        for parent_id in node["parent_ids"]:
            neighbors[parent_id].add(node_id)
    selected = {task_id}
    pending = [task_id]
    while pending:
        for neighbor in neighbors[pending.pop()] - selected:
            selected.add(neighbor)
            pending.append(neighbor)
    return selected


def _root_id(nodes: dict[str, dict[str, Any]], component: set[str]) -> str:
    roots = [task_id for task_id in component if not nodes[task_id]["parent_ids"]]
    return min(roots or component)


def list_task_graphs(root: Path, query: str, offset: int, limit: int) -> dict[str, Any]:
    nodes = _task_index(root)
    query = query.strip().casefold()
    selected = []
    seen: set[str] = set()
    for task_id, node in nodes.items():
        if node["missing"] or task_id in seen:
            continue
        component = _component(nodes, task_id)
        seen.update(component)
        matches = [
            nodes[item] for item in component
            if not nodes[item]["missing"]
            and (query in item.casefold() or query in nodes[item]["task_name"].casefold())
        ]
        if not matches:
            continue
        root_id = _root_id(nodes, component)
        representative = max(matches, key=lambda item: (item["created_at"] or "", item["task_id"])) if query else nodes.get(root_id)
        if representative is None or representative["missing"]:
            representative = min(matches, key=lambda item: item["task_id"])
        selected.append({**representative, "root_id": root_id})
    selected.sort(key=lambda node: (node["created_at"] or "", node["task_id"]), reverse=True)
    return {"items": selected[offset : offset + limit], "total": len(selected), "offset": offset, "limit": limit}


def get_task_graph(root: Path, task_id: str) -> dict[str, Any]:
    nodes = _task_index(root)
    if task_id not in nodes or nodes[task_id]["missing"]:
        raise ValueError(f"Task artifact not found: {task_id}")
    component = _component(nodes, task_id)
    graph = [nodes[item] for item in component]
    return {
        "root_id": _root_id(nodes, component),
        "selected_id": task_id,
        "nodes": sorted(graph, key=lambda node: (KINDS.index(node["kind"]), node["created_at"] or "", node["task_id"])),
        "edges": sorted(
            ({"from": parent_id, "to": node["task_id"]} for node in graph for parent_id in node["parent_ids"]),
            key=lambda edge: (edge["from"], edge["to"]),
        ),
    }
