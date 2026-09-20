"""Apply one staged Task archive on the receiving node."""

import asyncio
from contextlib import suppress

from ...components.registry import provider
from ...workspace.staging import StagedFiles
from .base import TaskRepositoryStep


@provider("sync_tasks_step")
class SyncTasksStep(TaskRepositoryStep):
    """Replace the task directories carried by one uploaded archive."""

    async def execute(self):
        path = self.context.get("path") or None
        staged_files = StagedFiles(self.workspace_path)
        try:
            archive = None if path is None else staged_files.file(path)
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
                    await asyncio.to_thread(staged_files.discard, path)
        self.response.answer = answer
