"""Task-listing step."""

from ...components import R
from ..common.base_step import BaseStep


@R.register("list_tasks")
class ListTasksStep(BaseStep):
    """Return all managed task identifiers."""

    async def execute(self):
        self.response.answer = await self.task_manager.list_task_ids()
