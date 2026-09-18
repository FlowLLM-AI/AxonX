"""Preview a workspace file."""

from ...components.registry import R
from ..base import BaseStep


@R.register("preview_file_step")
class PreviewFileStep(BaseStep):
    async def execute(self):
        self.response.answer = await self.workspace.preview_file(
            self.context["path"],
            self.context.get("offset", 0),
            self.context.get("limit", 200),
            self.context.get("full", False),
        )
