"""Periodically refreshed Task metadata index for application queries."""

from __future__ import annotations

import asyncio
import math
from collections.abc import AsyncIterator, Callable
from contextlib import suppress

from ....task.models.events import LogChunk, TaskEvent
from ....task.models.lifecycle import TaskMetadata
from ....task.models.query import TaskContextSnapshot, TaskGraph, TaskSummary
from ....task.storage.logs import TaskLogReader
from ....task.storage.workspace import FileVersion, read_entry, scan_metadata
from ....utils.async_work import run_blocking
from ..registry import provider
from .base import BaseTaskIndex, TaskChangeCallback
from .query import TaskQuery
from .stream import TaskEventStream


@provider("local")
class LocalTaskIndex(BaseTaskIndex):
    """Observe Task metadata without changing records or owning execution."""

    def __init__(self, poll_interval: float = 5, **kwargs) -> None:
        super().__init__(**kwargs)
        if not math.isfinite(poll_interval) or poll_interval <= 0:
            raise ValueError("poll_interval must be finite and positive")
        self.root = self.workspace.root
        self.logs = TaskLogReader(self.root)
        self.poll_interval = poll_interval
        self._query = TaskQuery({})
        self._versions: dict[str, FileVersion] = {}
        self._watch_task: asyncio.Task[None] | None = None
        self._subscribers: set[TaskChangeCallback] = set()

    async def _start(self) -> None:
        await self._refresh()
        self._watch_task = asyncio.create_task(self._poll(), name="axonx-task-index")

    async def _poll(self) -> None:
        while True:
            await asyncio.sleep(self.poll_interval)
            try:
                await self._refresh()
            except Exception:
                self.logger.exception("Task metadata polling failed; retrying")

    async def _close(self) -> None:
        watcher, self._watch_task = self._watch_task, None
        try:
            if watcher is not None:
                watcher.cancel()
                with suppress(asyncio.CancelledError):
                    await watcher
        finally:
            self._subscribers.clear()

    def subscribe(self, callback: TaskChangeCallback) -> Callable[[], None]:
        """Register a synchronous change callback; return its unsubscribe function."""
        if not self.is_started:
            raise RuntimeError("Task index is not running")
        self._subscribers.add(callback)
        return lambda: self._subscribers.discard(callback)

    async def _refresh(self) -> None:
        entries, versions = await run_blocking(scan_metadata, self.root, self._query.records, self._versions)
        changed_ids = frozenset(
            key for key in self._versions.keys() | versions.keys() if self._versions.get(key) != versions.get(key)
        )
        if not changed_ids:
            return
        self._query, self._versions = TaskQuery(entries), versions
        for callback in tuple(self._subscribers):
            try:
                callback(changed_ids)
            except Exception:
                self.logger.exception("Task change subscriber failed")

    async def entry(self, task_id: str) -> TaskMetadata:
        """Read fresh metadata for status, wait and stream queries."""
        metadata = await asyncio.to_thread(read_entry, self.root, task_id)
        if metadata is None:
            raise KeyError(task_id)
        return metadata

    async def entries(self, *, task_type: str | None = None, state: str | None = None) -> dict[str, TaskMetadata]:
        """Return isolated snapshots of matching indexed records."""
        return self._query.entries(task_type=task_type, state=state)

    async def summaries(self, *, task_type: str | None = None, state: str | None = None) -> list[TaskSummary]:
        """Project lightweight summaries without copying full outputs."""
        return self._query.summaries(task_type=task_type, state=state)

    async def graph(self, task_id: str) -> TaskGraph:
        """Build task relationships from indexed records."""
        return self._query.graph(task_id)

    async def context(self, task_id: str) -> TaskContextSnapshot:
        """Use fresh selected metadata with the current indexed dependencies."""
        status = await self.entry(task_id)
        return self._query.context(status)

    async def read_log(self, status: TaskMetadata, offset: int, limit: int) -> LogChunk:
        return await asyncio.to_thread(self.logs.read_status, status, offset, limit)

    def stream(self, task_id: str, poll_interval: float) -> AsyncIterator[TaskEvent]:
        return TaskEventStream(self.root, self.logs, self.entry, self.logger).follow(task_id, poll_interval)
