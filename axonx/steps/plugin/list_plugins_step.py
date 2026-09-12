"""Installed-plugin listing step."""

from ...components import R
from ..common.base_step import BaseStep


@R.register("list_plugins_step")
class ListPluginsStep(BaseStep):
    """Return the installed plugin status."""

    async def execute(self):
        self.response.answer = self.plugin.status()
