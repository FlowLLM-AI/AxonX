"""Task-history deletion step."""

from ...components.registry import R
from ..base import BaseStep


@R.register("delete_tasks")
class DeleteTasksStep(BaseStep):
    """Delete multiple terminal task records."""

    async def execute(self):
        self.response.answer = await self.task_manager.delete(self.context["task_ids"])
