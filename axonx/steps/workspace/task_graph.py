"""Task graph Job adapters."""

from ...components.registry import R
from ..base import BaseStep


@R.register("list_task_graphs_step")
class ListTaskGraphsStep(BaseStep):
    async def execute(self):
        self.response.answer = await self.task_manager.list_graphs(
            self.context.get("q", ""),
            self.context.get("offset", 0),
            self.context.get("limit", 50),
        )


@R.register("get_task_graph_step")
class GetTaskGraphStep(BaseStep):
    async def execute(self):
        self.response.answer = await self.task_manager.get_graph(self.context["task_id"])
