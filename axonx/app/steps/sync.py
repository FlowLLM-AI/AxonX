"""Job adapters for replica application, transfer and reconciliation indexes."""

import asyncio
from contextlib import suppress

from ...utils.async_work import run_blocking
from ..components.registry import provider
from ..components.sync.applier import FileSyncStore
from ..components.sync.base import BaseSyncComponent
from .base import BaseStep


@provider("sync_files_step")
class SyncFilesStep(BaseStep):
    """Commit the complete file inventory carried by one staged archive."""

    async def execute(self):
        path = self.context["path"]
        try:
            archive = self.workspace.uploads.file(path)
            answer = await run_blocking(
                FileSyncStore(self.workspace_path, self.app_config.transfer_budget_bytes).apply,
                archive,
                path,
            )
        except (OSError, TypeError, ValueError) as exc:
            self.response.success = False
            self.response.answer = str(exc)
            return
        finally:
            with suppress(OSError, TypeError, ValueError):
                await asyncio.to_thread(self.workspace.uploads.discard, path)
        self.response.answer = answer


@provider("sync_flush_step")
class SyncFlushStep(BaseStep):
    """Run one bounded sync round; scheduling remains configuration policy."""

    async def execute(self):
        self.response.answer = await self.component(BaseSyncComponent).flush()


@provider("sync_index_step")
class SyncIndexStep(BaseStep):
    async def execute(self):
        store = FileSyncStore(self.workspace_path, self.app_config.transfer_budget_bytes)
        self.response.answer = {
            "transfer_budget_bytes": self.app_config.transfer_budget_bytes,
            "groups": await asyncio.to_thread(store.index, self.context["source"]),
        }
