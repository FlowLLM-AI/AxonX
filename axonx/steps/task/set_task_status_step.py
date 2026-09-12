"""Task-status update step."""

from ...components import R
from ...schema import TaskStatus
from ..common.base_step import BaseStep


@R.register("set_task_status")
class SetTaskStatusStep(BaseStep):
    """Persist a complete task-status snapshot."""

    async def execute(self):
        status = TaskStatus.model_validate(self.context["status"])
        await self.task_manager.set_status(self.context["task_id"], status)
        self.response.answer = None
