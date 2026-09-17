"""Installed Task-listing step."""

from ...components.registry import R
from ...task.resolver import list_installed_task_definitions
from ..base import BaseStep


@R.register("list_installed_task_definitions")
class ListInstalledTaskDefinitionsStep(BaseStep):
    """Return definitions for every installed Task."""

    async def execute(self):
        definitions = list_installed_task_definitions()
        self.response.answer = [definition.model_dump(mode="json") for definition in definitions]
