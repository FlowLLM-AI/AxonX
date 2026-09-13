"""Task-cancellation step."""

from ...components.registry import R
from ..base import BaseStep


@R.register("cancel_task")
class CancelTaskStep(BaseStep):
    """Cancel a managed task."""

    async def execute(self):
        self.response.answer = await self.task_manager.cancel(self.context["task_id"])
