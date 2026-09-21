"""Agent-oriented Task context Step."""

from ...components.registry import provider
from ...enums import ComponentEnum
from ...task.storage.workspace import METADATA_FILE, task_directory
from ..base import BaseStep


@provider("get_task_context_step")
class GetTaskContextStep(BaseStep):
    component_domains = (ComponentEnum.TASK_MANAGER,)

    async def execute(self):
        task_id = self.context["task_id"]
        status = await self.task_manager.get_status(task_id)
        graph = await self.task_manager.get_graph(task_id)
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
        self.response.answer = {
            "task_id": task_id,
            "status": status,
            "metadata_exists": not selected.missing and not selected.provisional,
            "metadata_path": f"{task_directory(task_id)}/{METADATA_FILE}",
            "log_path": status.log_path or None,
            "graph": graph,
            "relations": {
                "direct_upstream": sorted(parents.get(task_id, ())),
                "ancestors": sorted(ancestors),
                "direct_downstream": sorted(
                    edge.to for edge in graph.edges if edge.from_ == task_id
                ),
                "missing": sorted(node.task_id for node in graph.nodes if node.missing),
                "provisional": sorted(
                    node.task_id for node in graph.nodes if node.provisional
                ),
            },
        }
