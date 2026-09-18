"""List workspace entries."""

from ...components.registry import R
from ..base import BaseStep


@R.register("list_entries_step")
class ListEntriesStep(BaseStep):
    async def execute(self):
        self.response.answer = await self.workspace.list_entries(
            self.context.get("path", ""), self.context.get("require_metadata", False)
        )
