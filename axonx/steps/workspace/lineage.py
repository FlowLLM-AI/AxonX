"""Index task artifacts and build their ETL lineage graph."""

import json
from pathlib import Path
from typing import Any

KINDS = ("etl", "analysis", "train", "predict", "backtest")
PARENTS = {
    "analysis": ("etl_task_id", "etl"),
    "train": ("etl_task_id", "etl"),
    "predict": ("train_task_id", "train"),
    "backtest": ("prediction_task_id", "predict"),
}


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
            if metadata.get("task_id") != task_dir.name or metadata.get("task_type") != kind:
                continue
            parent_id = None
            if kind in PARENTS:
                key, _parent_kind = PARENTS[kind]
                source = metadata.get("source_tasks")
                value = source.get(key) if isinstance(source, dict) else None
                if isinstance(value, str) and "#" in value and Path(value).name == value:
                    parent_id = value
            nodes[task_dir.name] = {
                "task_id": task_dir.name,
                "kind": kind,
                "task_name": metadata.get("reg_name") if isinstance(metadata.get("reg_name"), str) else kind,
                "created_at": metadata.get("created_at") if isinstance(metadata.get("created_at"), str) else None,
                "parent_id": parent_id,
                "missing": False,
            }
    return nodes


def _root_id(nodes: dict[str, dict[str, Any]], task_id: str) -> str:
    current = task_id
    seen: set[str] = set()
    while current in nodes and current not in seen:
        seen.add(current)
        parent = nodes[current]["parent_id"]
        if not parent:
            break
        current = parent
    return current


def list_task_graphs(root: Path, query: str, offset: int, limit: int) -> dict[str, Any]:
    nodes = _task_index(root)
    query = query.strip().casefold()
    selected = [
        {**node, "root_id": _root_id(nodes, node["task_id"])}
        for node in nodes.values()
        if (query in node["task_id"].casefold() or query in node["task_name"].casefold())
        and (query or node["kind"] == "etl")
    ]
    selected.sort(key=lambda node: (node["created_at"] or "", node["task_id"]), reverse=True)
    return {"items": selected[offset : offset + limit], "total": len(selected), "offset": offset, "limit": limit}


def get_task_graph(root: Path, task_id: str) -> dict[str, Any]:
    nodes = _task_index(root)
    if task_id not in nodes:
        raise ValueError(f"Task artifact not found: {task_id}")
    root_id = _root_id(nodes, task_id)
    graph = {node_id: dict(node) for node_id, node in nodes.items() if _root_id(nodes, node_id) == root_id}
    for node in tuple(graph.values()):
        parent_id = node["parent_id"]
        if parent_id and parent_id not in graph:
            graph[parent_id] = {
                "task_id": parent_id,
                "kind": PARENTS[node["kind"]][1],
                "task_name": None,
                "created_at": None,
                "parent_id": None,
                "missing": True,
            }
    return {
        "root_id": root_id,
        "selected_id": task_id,
        "nodes": sorted(
            graph.values(), key=lambda node: (KINDS.index(node["kind"]), node["created_at"] or "", node["task_id"])
        ),
        "edges": [{"from": node["parent_id"], "to": node["task_id"]} for node in graph.values() if node["parent_id"]],
    }
