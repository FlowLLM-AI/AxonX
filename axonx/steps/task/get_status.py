"""Task-status query step."""

from ...components.registry import R
from ..base import BaseStep


@R.register("get_task_status")
class GetTaskStatusStep(BaseStep):
    """Return one managed task status."""

    async def execute(self):
        task_id = self.context["task_id"]
        try:
            status = await self.task_manager.get_status(task_id)
        except KeyError:
            self.response.success = False
            self.response.answer = f"Task not found: {task_id}"
            return
        self.response.answer = status.model_dump(mode="json")
