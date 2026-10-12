"""Expose a terminal Task snapshot index for source startup reconciliation."""

import asyncio

from ...components.registry import provider
from ...task.sync.index import snapshot_index, validate_task_names
from ..base import BaseStep


@provider("task_sync_index_step")
class TaskSyncIndexStep(BaseStep):
    async def execute(self):
        names = validate_task_names(self.context.get("task_names"))
        self.response.answer = {
            "transfer_budget_bytes": self.app_config.transfer_budget_bytes,
            "tasks": await asyncio.to_thread(snapshot_index, self.workspace_path, names),
        }
