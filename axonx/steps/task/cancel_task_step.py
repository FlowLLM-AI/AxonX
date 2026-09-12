"""Task-cancellation step."""

from ...components import R
from ..common.base_step import BaseStep


@R.register("cancel_task")
class CancelTaskStep(BaseStep):
    """Cancel a managed task."""

    async def execute(self):
        self.response.answer = await self.task_manager.cancel(self.context["task_id"])
