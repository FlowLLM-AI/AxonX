"""Expose installed Task plugins through a standard job."""

from ...components import R
from ..base_step import BaseStep


@R.register("list_plugins_step")
class ListPluginsStep(BaseStep):
    """List plugins known to the local plugin component."""

    async def execute(self):
        self.response.answer = self.plugin.status()
