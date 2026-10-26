"""Expose a Task snapshot index for replica reconciliation."""

import asyncio

from ..base import BaseStep
from ...registry import provider
from ....task.sync.index import snapshot_index, validate_live_task_ids, validate_task_names


@provider("task_sync_index_step")
class TaskSyncIndexStep(BaseStep):
    async def execute(self):
        names = validate_task_names(self.context.get("task_names"))
        roots = validate_live_task_ids(self.context.get("live_task_ids"))
        self.response.answer = {
            "transfer_budget_bytes": self.app_config.transfer_budget_bytes,
            "tasks": await asyncio.to_thread(snapshot_index, self.workspace_path, names, roots),
        }
