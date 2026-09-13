"""Runtime Task-listing step."""

from ...components.registry import R
from ..base import BaseStep


@R.register("list_runtime_task_ids")
class ListRuntimeTaskIdsStep(BaseStep):
    """Return all known runtime Task identifiers."""

    async def execute(self):
        self.response.answer = await self.task_manager.list_runtime_task_ids()
