"""Agent-oriented Task context Step."""

from ...components.component_type import ComponentType
from ..base import BaseStep
from ...registry import provider


@provider("get_task_context_step")
class GetTaskContextStep(BaseStep):
    component_domains = (ComponentType.TASK_INDEX,)

    async def execute(self):
        task_id = self.context["task_id"]
        self.response.answer = await self.task_index.context(task_id)
