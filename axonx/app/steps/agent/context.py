"""Agent-oriented Task context Step."""

from ....common.registry import provider
from ....task.query.context import task_context
from ...components.types import ComponentEnum
from ..base import BaseStep


@provider("get_task_context_step")
class GetTaskContextStep(BaseStep):
    component_domains = (ComponentEnum.TASK_REPOSITORY,)

    async def execute(self):
        task_id = self.context["task_id"]
        status = await self.task_repository.entry(task_id)
        graph = await self.task_repository.graph(task_id)
        self.response.answer = task_context(status, graph)
