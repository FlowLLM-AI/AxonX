"""Periodically refreshed Task metadata index for application queries."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Callable
from contextlib import suppress

from .base import BaseTaskIndex, TaskChangeCallback
from ....common.async_work import run_blocking
from ....common.registry import provider
from ....task.models.lifecycle import TaskMetadata
from ....task.models.query import TaskGraph, TaskSummary
from ....task.query.graph import task_graph
from ....task.query.summary import summarize_status, task_sort_key
from ....task.storage.index import FileVersion, scan_metadata
from ....task.storage.workspace import read_entry


@provider("local")
class LocalTaskIndex(BaseTaskIndex):
    """Index metadata and reconcile dead local Runs without owning execution."""

    def __init__(self, poll_interval: float = 5, **kwargs) -> None:
        super().__init__(**kwargs)
        if not math.isfinite(poll_interval) or poll_interval <= 0:
            raise ValueError("poll_interval must be finite and positive")
        self.root = self.workspace.root
        self.poll_interval = poll_interval
        self._entries: dict[str, TaskMetadata] = {}
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
        changed.update(
            key for key, entry in entries.items() if key in self._entries and entry.state != self._entries[key].state
        )
        self._entries, self._versions = entries, versions
        if changed:
            for callback in tuple(self._subscribers):
                callback(frozenset(changed))

    async def entry(self, task_id: str) -> TaskMetadata:
        """Read fresh metadata for status, wait and stream queries."""
        metadata = await asyncio.to_thread(read_entry, self.root, task_id)
        if metadata is None:
            raise KeyError(task_id)
        return metadata

    async def entries(self, *, task_type: str | None = None, state: str | None = None) -> dict[str, TaskMetadata]:
        """Return isolated snapshots of matching indexed records."""
        return {
            task_id: metadata.model_copy(deep=True)
            for task_id, metadata in self._entries.items()
            if (task_type is None or metadata.task_type == task_type) and (state is None or metadata.state == state)
        }

    async def summaries(self, *, task_type: str | None = None, state: str | None = None) -> list[TaskSummary]:
        """Project lightweight summaries without copying full outputs."""
        return [
            summarize_status(metadata)
            for metadata in sorted(self._entries.values(), key=task_sort_key, reverse=True)
            if (task_type is None or metadata.task_type == task_type) and (state is None or metadata.state == state)
        ]

    async def graph(self, task_id: str) -> TaskGraph:
        """Build task relationships from indexed records."""
        return task_graph(self._entries, task_id)
