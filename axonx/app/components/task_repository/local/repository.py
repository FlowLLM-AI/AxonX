"""Indexed and observable local Task workspace."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Mapping
from contextlib import suppress
from pathlib import Path

from .....common.async_work import run_blocking
from .....common.registry import provider
from .....task.query.graph import TaskGraph, task_graph
from .....task.query.summary import TaskSummary, summarize_status, task_sort_key
from .....task.schemas.lifecycle import TaskMetadata
from .....task.storage.index import FileVersion, scan_metadata
from .....task.storage.workspace import read_entry
from .....task.sync import SyncTasksReport, TaskArchiveApplier
from ..base import BaseTaskRepository
from ..subscription import TaskChanges, TaskChangeSubscription


@provider("local")
class LocalTaskRepository(BaseTaskRepository):
    """Observe the local Task workspace through periodically refreshed snapshots."""

    def __init__(self, poll_interval: float = 1, **kwargs) -> None:
        super().__init__(**kwargs)
        if not math.isfinite(poll_interval) or poll_interval <= 0:
            raise ValueError("poll_interval must be finite and positive")
        self.root = self.workspace.root
        self.poll_interval = poll_interval
        self._entries: dict[str, TaskMetadata] = {}
        self._versions: dict[str, FileVersion] = {}
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
        entries, versions = await run_blocking(
            scan_metadata, self.root, dict(self._entries), dict(self._versions), force
        )
        changed = frozenset(
            task_id
            for task_id in self._versions.keys() | versions.keys()
            if self._versions.get(task_id) != versions.get(task_id)
        )
        self._entries, self._versions = entries, versions
        return TaskChanges(changed)

    async def entries(self, *, task_type: str | None = None, state: str | None = None) -> Mapping[str, TaskMetadata]:
        return {
            task_id: metadata.model_copy(deep=True)
            for task_id, metadata in self._entries.items()
            if (task_type is None or metadata.task_type == task_type) and (state is None or metadata.state == state)
        }

    async def entry(self, task_id: str) -> TaskMetadata:
        return self._entries[task_id].model_copy(deep=True)

    async def summaries(self, *, task_type: str | None = None, state: str | None = None) -> list[TaskSummary]:
        return [
            summarize_status(metadata)
            for metadata in sorted(self._entries.values(), key=task_sort_key, reverse=True)
            if (task_type is None or metadata.task_type == task_type) and (state is None or metadata.state == state)
        ]

    async def graph(self, task_id: str) -> TaskGraph:
        return task_graph(self._entries, task_id)

    async def apply_sync(
        self,
        archive_path: Path | None,
        deletions: list[str],
        archive_name: str | None,
    ) -> SyncTasksReport:
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
