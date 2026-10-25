"""Apply one staged Task archive on the receiving node."""

import asyncio
from contextlib import suppress

from ....common.registry import provider
from .base import TaskRepositoryStep


@provider("sync_tasks_step")
class SyncTasksStep(TaskRepositoryStep):
    """Replace the task directories carried by one uploaded archive."""

    async def execute(self):
        path = self.context.get("path") or None
        try:
            archive = None if path is None else self.workspace.staged_file(path)
            answer = await self.task_repository.apply_sync(
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
                    await asyncio.to_thread(self.workspace.discard_staged, path)
        self.response.answer = answer
