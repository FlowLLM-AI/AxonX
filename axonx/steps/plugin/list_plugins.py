"""Installed-plugin listing step."""

import asyncio

from ...components.registry import R
from ..base import BaseStep


@R.register("list_plugins_step")
class ListPluginsStep(BaseStep):
    """Return the installed plugin status."""

    async def execute(self):
        self.response.answer = self.plugin.status()


@R.register("status_plugins_step")
class StatusPluginsStep(BaseStep):
    """Return one plugin's saved status from the addressed service."""

    async def execute(self):
        self.response.answer = self.plugin.plugin_status(self.context["plugin"])


@R.register("inspect_plugins_step")
class InspectPluginsStep(BaseStep):
    """Inspect a managed wheel on the addressed service machine."""

    async def execute(self):
        self.response.answer = await asyncio.to_thread(self.plugin.inspect, self.context["plugin"])
