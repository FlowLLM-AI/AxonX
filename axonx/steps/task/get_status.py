"""Task-status query step."""

from ...components.registry import R
from ..base import BaseStep


@R.register("get_task_status")
class GetTaskStatusStep(BaseStep):
    """Return one managed task status."""

    async def execute(self):
        status = await self.task_manager.get_status(self.context["task_id"])
        self.response.answer = status.model_dump(mode="json")
