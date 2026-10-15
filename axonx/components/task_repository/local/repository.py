"""Indexed and observable local Task workspace."""

from __future__ import annotations

import asyncio
import shutil
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path

from ....task.query.graph import TaskGraph, task_graph
from ....task.query.summary import TaskSummary, summarize_status, task_sort_key
from ....task.storage.workspace import (
    TaskMetadata,
    is_task_directory,
    read_entry,
    reset_task_directory,
    scan_entries,
    task_path,
    write_task_metadata,
)
from ....task.sync import SyncTasksReport, TaskArchiveApplier
from ....utils.async_work import run_blocking
from ...registry import provider
from ..base import BaseTaskRepository
from ..subscription import TaskChanges, TaskChangeSubscription
from .watcher import TaskWorkspaceWatcher


@provider("local")
class LocalTaskRepository(BaseTaskRepository):
    """Own one coherent in-memory view of the local Task workspace."""

    def __init__(
        self,
        recursive: bool = True,
        force_polling: bool = True,
        debounce: int = 3_000,
        step: int = 3_000,
        poll_delay_ms: int = 1_000,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.root = self.workspace_path.expanduser().resolve()
        self._entries: dict[str, TaskMetadata] = {}
        self._lock = asyncio.Lock()
        self._subscriptions: set[TaskChangeSubscription] = set()
        self._watcher = TaskWorkspaceWatcher(
            self.root,
            {
                "recursive": recursive,
                "force_polling": force_polling,
                "debounce": debounce,
                "step": step,
                "poll_delay_ms": poll_delay_ms,
            },
            self._handle_changes,
            self.logger,
        )
        self._watch_task: asyncio.Task[None] | None = None

    async def _start(self) -> None:
        await self.reconcile()
        self._watch_task = asyncio.create_task(self._watcher.run(), name="axonx-task-repository")
        await asyncio.sleep(0)
        await self.reconcile()

    async def _close(self) -> None:
        if self._watch_task is not None:
            self._watch_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._watch_task
            self._watch_task = None
        for subscription in tuple(self._subscriptions):
            subscription.close()

    def subscribe(self) -> TaskChangeSubscription:
        if not self.is_started:
            raise RuntimeError("Task repository is not running")
        subscription = TaskChangeSubscription(self._subscriptions.discard)
        self._subscriptions.add(subscription)
        return subscription

    async def reconcile(self) -> None:
        async with self._lock:
            self._entries = await asyncio.to_thread(scan_entries, self.root)

    async def entries(self, *, task_type: str | None = None, state: str | None = None) -> Mapping[str, TaskMetadata]:
        async with self._lock:
            return {
                task_id: metadata.model_copy(deep=True)
                for task_id, metadata in self._entries.items()
                if (task_type is None or metadata.task_type == task_type) and (state is None or metadata.state == state)
            }

    async def entry(self, task_id: str) -> TaskMetadata:
        async with self._lock:
            return self._entries[task_id].model_copy(deep=True)

    async def summaries(self, *, task_type: str | None = None, state: str | None = None) -> list[TaskSummary]:
        async with self._lock:
            return [
                summarize_status(metadata)
                for metadata in sorted(self._entries.values(), key=task_sort_key, reverse=True)
                if (task_type is None or metadata.task_type == task_type) and (state is None or metadata.state == state)
            ]

    async def graph(self, task_id: str) -> TaskGraph:
        async with self._lock:
            return task_graph(self._entries, task_id)

    async def put_metadata(self, status: TaskMetadata) -> None:
        async with self._lock:
            directory = task_path(self.root, status.task_id)
            if not is_task_directory(directory, strict_io=True):
                return
            await asyncio.to_thread(write_task_metadata, directory, status)
            self._entries[status.task_id] = status.model_copy(deep=True)

    async def forget(self, task_id: str) -> None:
        async with self._lock:
            self._entries.pop(task_id, None)

    async def delete_terminal(self, task_id: str) -> bool:
        return await self._clear_terminal(task_id, reset=False)

    async def reset_terminal(self, task_id: str) -> bool:
        return await self._clear_terminal(task_id, reset=True)

    async def _clear_terminal(self, task_id: str, *, reset: bool) -> bool:
        async with self._lock:
            directory = task_path(self.root, task_id)
            if directory.is_symlink() or directory.parent.is_symlink():
                return False
            entry = await asyncio.to_thread(read_entry, self.root, task_id)
            if entry is None or not entry.state.is_terminal:
                return False
            try:
                await asyncio.to_thread(reset_task_directory if reset else shutil.rmtree, directory)
            except FileNotFoundError:
                if directory.exists():
                    raise
            self._entries.pop(task_id, None)
            return True

    async def _handle_changes(self, changes: TaskChanges) -> None:
        if changes.resync:
            await self.reconcile()
        else:
            async with self._lock:
                for task_id in changes.task_ids:
                    entry = await asyncio.to_thread(read_entry, self.root, task_id)
                    if entry is None:
                        self._entries.pop(task_id, None)
                    else:
                        self._entries[task_id] = entry
        self._publish(changes)

    async def apply_sync(
        self,
        archive_path: Path | None,
        deletions: list[str],
        archive_name: str | None,
    ) -> SyncTasksReport:
        async with self._lock:
            report = await run_blocking(
                TaskArchiveApplier(self.root, self.app_config.transfer_budget_bytes).apply,
                archive_path,
                deletions,
                archive_name,
            )
            for relative_path in report.applied + report.deleted:
                task_id = relative_path.split("/", 1)[1]
                entry = await asyncio.to_thread(read_entry, self.root, task_id)
                if entry is None:
                    self._entries.pop(task_id, None)
                else:
                    self._entries[task_id] = entry
        changed = frozenset(path.split("/", 1)[1] for path in report.applied + report.deleted)
        self._publish(TaskChanges(changed))
        return report

    def _publish(self, changes: TaskChanges) -> None:
        for subscription in tuple(self._subscriptions):
            subscription.publish(changes)
