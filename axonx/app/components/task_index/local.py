"""Periodically refreshed Task metadata index for application queries."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Callable, Iterator
from contextlib import suppress
from pathlib import Path

from ....task.models.events import LogChunk
from ....task.models.lifecycle import TaskMetadata
from ....task.models.query import TaskContextSnapshot, TaskGraph, TaskSummary
from ....task.storage.logs import TaskLogReader
from ....task.storage.workspace import FileVersion, read_entry, scan_metadata
from ....utils.async_work import run_blocking
from ..registry import provider
from .base import BaseTaskIndex, TaskChangeCallback
from .query import TaskGraphQuery, summarize_status, task_sort_key
from .stream import TaskEventStream


@provider("local")
class LocalTaskIndex(BaseTaskIndex):
    """Observe Task metadata without changing records or owning execution."""

    def __init__(self, poll_interval: float = 5, **kwargs) -> None:
        super().__init__(**kwargs)
        if not math.isfinite(poll_interval) or poll_interval <= 0:
            raise ValueError("poll_interval must be finite and positive")
        self.root = self.workspace.root
        self.logs = TaskLogReader(Path(self.app_config.log_dir).expanduser().resolve())
        self.poll_interval = poll_interval
        self._entries: dict[str, TaskMetadata] = {}
        self._graph = TaskGraphQuery(self._entries)
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
        if self._watch_task is not None:
            self._watch_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._watch_task
            self._watch_task = None
        self._subscribers.clear()

    def subscribe(self, callback: TaskChangeCallback) -> Callable[[], None]:
        """Register a synchronous change callback; return its unsubscribe function."""
        if not self.is_started:
            raise RuntimeError("Task index is not running")
        self._subscribers.add(callback)
        return lambda: self._subscribers.discard(callback)

    async def _refresh(self) -> None:
        entries, versions = await run_blocking(scan_metadata, self.root, self._entries, self._versions)
        changed = {
            key for key in self._versions.keys() | versions.keys() if self._versions.get(key) != versions.get(key)
        }
        self._entries, self._versions = entries, versions
        if changed:
            self._graph = TaskGraphQuery(entries)
            changed_ids = frozenset(changed)
            for callback in tuple(self._subscribers):
                callback(changed_ids)

    async def entry(self, task_id: str) -> TaskMetadata:
        """Read fresh metadata for status, wait and stream queries."""
        metadata = await asyncio.to_thread(read_entry, self.root, task_id)
        if metadata is None:
            raise KeyError(task_id)
        return metadata

    def _matching(self, task_type: str | None, state: str | None) -> Iterator[TaskMetadata]:
        return (
            metadata
            for metadata in self._entries.values()
            if (task_type is None or metadata.task_type == task_type) and (state is None or metadata.state == state)
        )

    async def entries(self, *, task_type: str | None = None, state: str | None = None) -> dict[str, TaskMetadata]:
        """Return isolated snapshots of matching indexed records."""
        return {metadata.task_id: metadata.model_copy(deep=True) for metadata in self._matching(task_type, state)}

    async def summaries(self, *, task_type: str | None = None, state: str | None = None) -> list[TaskSummary]:
        """Project lightweight summaries without copying full outputs."""
        return [
            summarize_status(metadata)
            for metadata in sorted(self._matching(task_type, state), key=task_sort_key, reverse=True)
        ]

    async def graph(self, task_id: str) -> TaskGraph:
        """Build task relationships from indexed records."""
        return self._graph.graph(task_id)

    async def context(self, task_id: str) -> TaskContextSnapshot:
        status = await self.entry(task_id)
        return self._graph.context(status)

    async def read_log(self, status: TaskMetadata, offset: int, limit: int) -> LogChunk:
        return await asyncio.to_thread(self.logs.read_status, self.root, status, offset, limit)

    def stream(self, task_id: str, poll_interval: float):
        return TaskEventStream(self.root, self.logs, self.entry, self.logger).follow(task_id, poll_interval)
