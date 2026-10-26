"""Expose a Task snapshot index for replica reconciliation."""

import asyncio

from ....task.models.identity import validate_task_ids, validate_task_names
from ...components.sync.index import snapshot_index
from ...registry import provider
from ..base import BaseStep


@provider("task_sync_index_step")
class TaskSyncIndexStep(BaseStep):
    async def execute(self):
        names = validate_task_names(self.context.get("task_names"))
        roots = validate_task_ids(self.context.get("live_task_ids"))
        self.response.answer = {
            "transfer_budget_bytes": self.app_config.transfer_budget_bytes,
            "tasks": await asyncio.to_thread(snapshot_index, self.workspace_path, names, roots),
        }
