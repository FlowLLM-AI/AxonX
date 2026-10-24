"""Installed-plugin listing Job adapter."""

import asyncio

from ....plugin.registry import provider
from ....plugin import list_installed_plugins
from ..base import BaseStep


@provider("list_plugins_step")
class ListPluginsStep(BaseStep):
    """Return the installed plugin status."""

    async def execute(self):
        self.response.answer = await asyncio.to_thread(list_installed_plugins)
