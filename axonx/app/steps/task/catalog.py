"""Query Task definitions in the service's installed Python environment."""

from ....utils.async_work import run_blocking
from ...registry import provider
from ..base import BaseStep


@provider("list_task_defs")
class ListTaskDefsStep(BaseStep):
    """List registered Tasks, optionally including their parameter schemas."""

    async def execute(self):
        def query():
            from ....plugin.catalog import TaskCatalog

            return TaskCatalog().definitions(include_schemas=self.context.get("include_schemas", True))

        self.response.answer = await run_blocking(query)


@provider("get_task_def")
class GetTaskDefStep(BaseStep):
    """Describe one registered Task without loading unrelated Tasks."""

    async def execute(self):
        def query():
            from ....plugin.catalog import TaskCatalog

            return TaskCatalog().definition(self.context["task"])

        self.response.answer = await run_blocking(query)
