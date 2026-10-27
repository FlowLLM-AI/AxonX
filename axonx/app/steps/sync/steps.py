"""Job adapters for replica application, transfer and reconciliation indexes."""

import asyncio
from contextlib import suppress

from ....task.models.identity import validate_task_ids, validate_task_names
from ....utils.async_work import run_blocking
from ...components.models import ComponentType
from ...components.registry import provider
from ...components.sync.applier import TaskArchiveApplier
from ...components.sync.base import BaseSyncComponent
from ...components.sync.index import snapshot_index
from ..base import BaseStep


@provider("sync_tasks_step")
class SyncTasksStep(BaseStep):
    """Replace the task directories carried by one uploaded archive."""

    async def execute(self):
        path = self.context.get("path") or None
        try:
            archive = None if path is None else self.workspace.uploads.file(path)
            answer = await run_blocking(
                TaskArchiveApplier(self.workspace_path, self.app_config.transfer_budget_bytes).apply,
                archive,
                self.context.get("deletions", []),
                path,
            )
        except (OSError, TypeError, ValueError) as exc:
            self.response.success = False
            self.response.answer = str(exc)
            return
        finally:
            if path is not None:
                with suppress(OSError, TypeError, ValueError):
                    await asyncio.to_thread(self.workspace.uploads.discard, path)
        self.response.answer = answer


@provider("sync_flush_step")
class SyncFlushStep(BaseStep):
    """Run one bounded sync round; scheduling remains configuration policy."""

    component_domains = (ComponentType.SYNC,)

    async def execute(self):
        self.response.answer = await self.component(BaseSyncComponent).flush()


@provider("task_sync_index_step")
class TaskSyncIndexStep(BaseStep):
    async def execute(self):
        names = validate_task_names(self.context.get("task_names"))
        roots = validate_task_ids(self.context.get("live_task_ids"))
        self.response.answer = {
            "transfer_budget_bytes": self.app_config.transfer_budget_bytes,
            "tasks": await asyncio.to_thread(snapshot_index, self.workspace_path, names, roots),
        }
