"""Filesystem watcher used by the local Task repository."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from pathlib import Path
from typing import Any

from watchfiles import awatch

from ....task.storage.workspace import ensure_kind_directories, task_id_from_path
from ..subscription import TaskChanges

ChangeHandler = Callable[[TaskChanges], Awaitable[None]]


class TaskWorkspaceWatcher:
    """Watch Task directories and recover from watcher failures."""

    def __init__(
        self, root: Path, options: dict[str, Any], handler: ChangeHandler, logger: Any
    ) -> None:
        self.root = root
        self.options = options
        self.handler = handler
        self.logger = logger
        self.directories: tuple[Path, ...] = ()

    async def run(self) -> None:
        recovering = False
        while True:
            self.directories = await asyncio.to_thread(
                ensure_kind_directories, self.root
            )
            pump = asyncio.create_task(self._pump(), name="axonx-task-repository-pump")
            try:
                await asyncio.sleep(0)
                if not pump.done() and recovering:
                    await self.handler(TaskChanges(resync=True))
                    recovering = False
                await pump
                raise RuntimeError("Task workspace watcher stopped unexpectedly")
            except asyncio.CancelledError:
                pump.cancel()
                with suppress(asyncio.CancelledError):
                    await pump
                raise
            except Exception:
                self.logger.exception("Task workspace watcher failed; retrying")
                recovering = True
                pump.cancel()
                with suppress(asyncio.CancelledError):
                    await pump
                await asyncio.sleep(1)

    async def _pump(self) -> None:
        async for changes in awatch(
            *self.directories,
            watch_filter=self._accept,
            **self.options,
        ):
            task_ids = frozenset(
                task_id
                for _, raw_path in changes
                if (task_id := task_id_from_path(self.root, raw_path)) is not None
            )
            if task_ids:
                await self.handler(TaskChanges(task_ids))

    def _accept(self, _change: object, raw_path: str) -> bool:
        return task_id_from_path(self.root, raw_path) is not None
