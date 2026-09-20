"""Indexed and observable local Task workspace."""

from __future__ import annotations

import asyncio
import shutil
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path

from ....task.storage.workspace import (
    TaskEntry,
    TaskRecord,
    TaskStatus,
    read_entry,
    scan_entries,
    task_path,
    write_status,
)
from ....task.sync import SyncTasksReport, TaskArchiveApplier
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
        if self.extra_options:
            options = ", ".join(sorted(self.extra_options))
            raise TypeError(f"Unsupported {type(self).__name__} options: {options}")
        self.root = self.workspace_path.expanduser().resolve()
        self._entries: dict[str, TaskEntry] = {}
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
        self._watch_task = asyncio.create_task(
            self._watcher.run(), name="axonx-task-repository"
        )
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

    async def entries(self) -> Mapping[str, TaskEntry]:
        async with self._lock:
            return dict(self._entries)

    async def entry(self, task_id: str) -> TaskEntry:
        async with self._lock:
            return self._entries[task_id]

    async def statuses(self) -> Mapping[str, TaskStatus]:
        async with self._lock:
            return {
                task_id: entry.status
                for task_id, entry in self._entries.items()
                if entry.status is not None
            }

    async def records(self) -> Mapping[str, TaskRecord]:
        async with self._lock:
            return {
                task_id: entry.record
                for task_id, entry in self._entries.items()
                if entry.record is not None
            }

    async def put_status(self, status: TaskStatus) -> None:
        async with self._lock:
            directory = task_path(self.root, status.task_id)
            if (
                not directory.is_dir()
                or directory.is_symlink()
                or directory.parent.is_symlink()
            ):
                return
            await asyncio.to_thread(write_status, directory, status)
            entry = self._entries.get(status.task_id)
            self._entries[status.task_id] = TaskEntry(
                status, entry.record if entry else None
            )

    async def forget(self, task_id: str) -> None:
        async with self._lock:
            self._entries.pop(task_id, None)

    async def delete_terminal(self, task_id: str) -> bool:
        async with self._lock:
            directory = task_path(self.root, task_id)
            if directory.is_symlink() or directory.parent.is_symlink():
                return False
            entry = await asyncio.to_thread(read_entry, self.root, task_id)
            if entry is None or (
                entry.status is not None and not entry.status.state.is_terminal
            ):
                return False
            try:
                await asyncio.to_thread(shutil.rmtree, directory)
            except FileNotFoundError:
                pass
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
            report = await asyncio.to_thread(
                TaskArchiveApplier(self.root).apply,
                archive_path,
                deletions,
                archive_name,
            )
            self._entries = await asyncio.to_thread(scan_entries, self.root)
        changed = frozenset(
            path.split("/", 1)[1] for path in report.applied + report.deleted
        )
        self._publish(TaskChanges(changed))
        return report

    def _publish(self, changes: TaskChanges) -> None:
        for subscription in tuple(self._subscriptions):
            subscription.publish(changes)
