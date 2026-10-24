"""Uninstall-plugin Job adapter."""

from ...components.registry import provider
from ...utils.async_work import run_blocking
from ...plugin_kit import uninstall_plugin
from ..base import BaseStep


@provider("uninstall_plugin_step")
class UninstallPluginStep(BaseStep):
    """Uninstall one plugin distribution from this service machine."""

    async def execute(self):
        self.response.answer = await run_blocking(uninstall_plugin, self.context["plugin"])
