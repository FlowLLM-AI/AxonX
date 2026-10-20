"""Indexed and observable local Task workspace."""

from __future__ import annotations

import asyncio
import math
import shutil
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path

from ....task.query.graph import TaskGraph, task_graph
from ....task.query.summary import TaskSummary, managed_runs, summarize_status, task_sort_key
from ....task.storage.locking import workspace_lock, workspace_mutation
from ....task.schemas.lifecycle import TaskMetadata
from ....task.storage.workspace import (
    is_task_directory,
    read_entry,
    reset_task_directory,
    task_path,
    write_task_metadata,
)
from ....task.sync import SyncTasksReport, TaskArchiveApplier
from ....utils.async_work import run_blocking
from ...registry import provider
from ..base import BaseTaskRepository
from ..subscription import TaskChanges, TaskChangeSubscription
from .index import FileVersion, scan_metadata


@provider("local")
class LocalTaskRepository(BaseTaskRepository):
    """Own one coherent in-memory view of the local Task workspace."""

    def __init__(self, poll_interval: float = 1, **kwargs) -> None:
        super().__init__(**kwargs)
        if not math.isfinite(poll_interval) or poll_interval <= 0:
            raise ValueError("poll_interval must be finite and positive")
        self.root = self.workspace_path.expanduser().resolve()
        self.poll_interval = poll_interval
        self._entries: dict[str, TaskMetadata] = {}
        self._versions: dict[str, FileVersion] = {}
        self._lock = asyncio.Lock()
        self._subscriptions: set[TaskChangeSubscription] = set()
        self._watch_task: asyncio.Task[None] | None = None

    async def _start(self) -> None:
        await self.reconcile()
        self._watch_task = asyncio.create_task(self._poll(), name="axonx-task-repository")

    async def _poll(self) -> None:
        while True:
            try:
                self._publish(await self._refresh())
            except Exception:
                self.logger.exception("Task metadata polling failed; retrying")
            await asyncio.sleep(self.poll_interval)

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
        await self._refresh(force=True)
        self._publish(TaskChanges(resync=True))

    async def _refresh(self, *, force: bool = False) -> TaskChanges:
        async with self._lock:
            entries, versions = await run_blocking(scan_metadata, self.root, self._entries, self._versions, force)
            changed = frozenset(
                task_id
                for task_id in self._versions.keys() | versions.keys()
                if self._versions.get(task_id) != versions.get(task_id)
            )
            self._entries, self._versions = entries, versions
        return TaskChanges(changed)

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

    async def managed_runs(self, owned: set[str]) -> dict[str, str]:
        async with self._lock:
            return managed_runs(self._entries, owned)

    async def put_metadata(self, status: TaskMetadata) -> None:
        async with self._lock:
            directory = task_path(self.root, status.task_id)
            if not is_task_directory(directory, strict_io=True):
                return
            await run_blocking(write_task_metadata, directory, status)
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
            try:
                cleared = await run_blocking(self._remove_terminal, task_id, reset)
            except BlockingIOError:
                return False
            except FileNotFoundError:
                if directory.exists():
                    raise
                cleared = True
            if not cleared:
                return False
            self._entries.pop(task_id, None)
            return True

    def _remove_terminal(self, task_id: str, reset: bool) -> bool:
        with workspace_lock(self.root, task_id):
            entry = read_entry(self.root, task_id)
            if entry is None or not entry.state.is_terminal:
                return False
            (reset_task_directory if reset else shutil.rmtree)(task_path(self.root, task_id))
            return True

    async def apply_sync(
        self,
        archive_path: Path | None,
        deletions: list[str],
        archive_name: str | None,
    ) -> SyncTasksReport:
        async with workspace_mutation(self.root):
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
        if not changes.task_ids and not changes.resync:
            return
        for subscription in tuple(self._subscriptions):
            subscription.publish(changes)
