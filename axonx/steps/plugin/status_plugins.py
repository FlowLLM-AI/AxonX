"""Managed-plugin status step."""

from ...components.registry import R
from ..base import BaseStep


@R.register("status_plugins_step")
class StatusPluginsStep(BaseStep):
    """Return one plugin's saved status from the addressed service."""

    async def execute(self):
        self.response.answer = self.plugin.plugin_status(self.context["plugin"])
