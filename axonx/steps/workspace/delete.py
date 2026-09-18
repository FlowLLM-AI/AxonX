"""Delete workspace entries."""

from ...components.registry import R
from ..base import BaseStep


@R.register("delete_entries_step")
class DeleteEntriesStep(BaseStep):
    async def execute(self):
        self.response.answer = await self.workspace.delete_entries(self.context["paths"])
