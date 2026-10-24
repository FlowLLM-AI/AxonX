"""Uninstall-plugin Job adapter."""

from ....plugin.registry import provider
from ....common.async_work import run_blocking
from ....plugin import uninstall_plugin
from ..base import BaseStep


@provider("uninstall_plugin_step")
class UninstallPluginStep(BaseStep):
    """Uninstall one plugin distribution from this service machine."""

    async def execute(self):
        self.response.answer = await run_blocking(uninstall_plugin, self.context["plugin"])
