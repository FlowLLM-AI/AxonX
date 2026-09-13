"""Runtime Task-status listing step."""

from ...components.registry import R
from ..base import BaseStep


@R.register("list_runtime_task_statuses")
class ListRuntimeTaskStatusesStep(BaseStep):
    """Return complete status snapshots for every managed Task."""

    async def execute(self):
        statuses = await self.task_manager.list_runtime_task_statuses()
        self.response.answer = [status.model_dump(mode="json") for status in statuses]
