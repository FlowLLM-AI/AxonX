"""Managed-plugin wheel inspection step."""

import asyncio

from ...components.registry import R
from ..base import BaseStep


@R.register("inspect_plugins_step")
class InspectPluginsStep(BaseStep):
    """Inspect a managed wheel on the addressed service machine."""

    async def execute(self):
        self.response.answer = await asyncio.to_thread(self.plugin.inspect, self.context["plugin"])
