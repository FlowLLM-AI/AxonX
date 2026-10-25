"""Agent-oriented Task context Step."""

from ...components.component_type import ComponentType
from ..base import BaseStep
from ....common.registry import provider
from ....task.query.context import task_context


@provider("get_task_context_step")
class GetTaskContextStep(BaseStep):
    component_domains = (ComponentType.TASK_INDEX,)

    async def execute(self):
        task_id = self.context["task_id"]
        status = await self.task_index.entry(task_id)
        graph = await self.task_index.graph(task_id)
        self.response.answer = task_context(status, graph)
