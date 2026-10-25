"""Build a Task context from persisted status and graph snapshots."""

from ..schemas.lifecycle import TaskMetadata
from ..storage.workspace import METADATA_FILE, task_directory
from .graph import TaskGraph


def task_context(status: TaskMetadata, graph: TaskGraph) -> dict:
    task_id = status.task_id
    nodes = {node.task_id: node for node in graph.nodes}
    parents = {node.task_id: set(node.parent_ids) for node in graph.nodes}

    ancestors: set[str] = set()
    visited = {task_id}
    pending = list(parents.get(task_id, ()))
    while pending:
        parent = pending.pop()
        if parent in visited:
            continue
        visited.add(parent)
        ancestors.add(parent)
        pending.extend(parents.get(parent, ()) - visited)

    selected = nodes[task_id]
    return {
        "task_id": task_id,
        "status": status,
        "metadata_exists": not selected.missing,
        "metadata_path": f"{task_directory(task_id)}/{METADATA_FILE}",
        "log_path": status.log_path or None,
        "graph": graph,
        "relations": {
            "direct_upstream": sorted(parents.get(task_id, ())),
            "ancestors": sorted(ancestors),
            "direct_downstream": sorted(edge.to for edge in graph.edges if edge.from_ == task_id),
            "missing": sorted(node.task_id for node in graph.nodes if node.missing),
            "provisional": sorted(node.task_id for node in graph.nodes if node.provisional),
        },
    }
