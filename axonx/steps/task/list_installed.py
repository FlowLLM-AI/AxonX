"""Installed Task-listing step."""

from ...components.registry import R
from ...task.resolver import list_installed_task_infos
from ..base import BaseStep


@R.register("list_installed_task_infos")
class ListInstalledTaskInfosStep(BaseStep):
    """Return metadata for every installed Task."""

    async def execute(self):
        infos = list_installed_task_infos()
        self.response.answer = [info.model_dump(mode="json") for info in infos]
