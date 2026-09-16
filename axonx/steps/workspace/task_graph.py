"""Task graph Job adapters."""

import asyncio

from ...components.registry import R
from ..base import BaseStep
from .lineage import get_task_graph, list_task_graphs
from .paths import workspace_root


@R.register("list_task_graphs_step")
class ListTaskGraphsStep(BaseStep):
    async def execute(self):
        self.response.answer = await asyncio.to_thread(
            list_task_graphs,
            workspace_root(self.app_config.workspace_dir),
            self.context.get("q", ""),
            self.context.get("offset", 0),
            self.context.get("limit", 50),
        )


@R.register("get_task_graph_step")
class GetTaskGraphStep(BaseStep):
    async def execute(self):
        self.response.answer = await asyncio.to_thread(
            get_task_graph,
            workspace_root(self.app_config.workspace_dir),
            self.context["task_id"],
        )
