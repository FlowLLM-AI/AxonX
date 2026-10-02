"""Uninstall-plugin Job adapter."""

import asyncio

from ...components.registry import provider
from ...plugin_kit import uninstall_plugin
from ..base import BaseStep


@provider("uninstall_plugin_step")
class UninstallPluginStep(BaseStep):
    """Uninstall one plugin distribution from this service machine."""

    async def execute(self):
        self.response.answer = await asyncio.to_thread(uninstall_plugin, self.context["plugin"])
