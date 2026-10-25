"""Read Task definitions through a separate CLI process."""

import json

from ..common.cli import CliStep
from ....common.registry import provider


class TaskCatalogStep(CliStep):
    action: str

    async def execute(self):
        self.context["argv"] = [self.action]
        for key, value in self.context.items():
            if key in {"task", "include_schemas"}:
                self.context["argv"].extend(
                    ["--" + key.replace("_", "-"), str(value).lower() if isinstance(value, bool) else str(value)]
                )
        await super().execute()
        if self.response.success:
            self.response.answer = json.loads(self.response.answer["stdout"])


@provider("list_installed_task_definitions")
class ListInstalledTaskDefinitionsStep(TaskCatalogStep):
    action = "list_installed_task_definitions"


@provider("get_task_definition")
class GetTaskDefinitionStep(TaskCatalogStep):
    action = "get_task_definition"
