"""Query Task definitions in the service's installed Python environment."""

from ....utils.async_work import run_blocking
from ...components.registry import provider
from ..base import BaseStep


@provider("list_task_defs")
class ListTaskDefsStep(BaseStep):
    """List registered Tasks, optionally including their parameter schemas."""

    async def execute(self):
        def query():
            return self.app_context.task_catalog.definitions(include_schemas=self.context.get("include_schemas", True))

        self.response.answer = await run_blocking(query)


@provider("get_task_def")
class GetTaskDefStep(BaseStep):
    """Describe one registered Task without loading unrelated Tasks."""

    async def execute(self):
        self.response.answer = await run_blocking(self.app_context.task_catalog.definition, self.context["task"])
