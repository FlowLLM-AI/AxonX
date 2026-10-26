"""Agent-oriented Task context Step."""

from ...components.component_type import ComponentType
from ...registry import provider
from ..base import BaseStep


@provider("get_task_context_step")
class GetTaskContextStep(BaseStep):
    component_domains = (ComponentType.TASK_INDEX,)

    async def execute(self):
        task_id = self.context["task_id"]
        self.response.answer = await self.task_index.context(task_id)
