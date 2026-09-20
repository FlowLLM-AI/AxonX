"""Installed Task catalog Steps."""

from ...components.registry import provider
from ...task.catalog import list_installed_task_definitions
from ..base import BaseStep


@provider("list_installed_task_definitions")
class ListInstalledTaskDefinitionsStep(BaseStep):
    """Return definitions for every installed Task."""

    async def execute(self):
        self.response.answer = list_installed_task_definitions()
