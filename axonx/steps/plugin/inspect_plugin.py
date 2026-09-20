"""Installed-plugin inspection Job adapter."""

import asyncio

from ...components.registry import provider
from ...plugin_kit import get_installed_plugin
from ..base import BaseStep


@provider("inspect_plugin_step")
class InspectPluginStep(BaseStep):
    """Inspect one plugin installed on the addressed machine."""

    async def execute(self):
        self.response.answer = await asyncio.to_thread(
            get_installed_plugin, self.context["plugin"]
        )
