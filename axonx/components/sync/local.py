"""Reconcile terminal Task snapshots on startup and send subsequent changes once."""

from __future__ import annotations

import asyncio
import tempfile
from collections.abc import Sequence
from contextlib import suppress
from pathlib import Path

from ...config import TargetConfig
from ...constants import MAX_ARCHIVE_BYTES
from ...task.storage.workspace import read_task_metadata, task_directory, task_path
from ...task.sync import (
    SYNC_ARCHIVE_NAME,
    SyncReport,
    TaskPlan,
    archive_budget,
    build_archive,
    pack_batches,
    plan_task,
)
from ...task.sync.index import matches_task_name, snapshot_index, validate_task_names
from ...utils.fs import file_sha256
from ..client import HttpClient
from ..registry import provider
from ..task_repository import BaseTaskRepository, TaskChangeSubscription
from .base import BaseSyncComponent

MAX_FILE_BYTES = 100 * 1024 * 1024
MAX_ARCHIVES_PER_FLUSH = 4
SYNC_TIMEOUT_SECONDS = 300.0


@provider("local")
class LocalSyncComponent(BaseSyncComponent):
    """Keep an in-memory queue; failed transfers are repaired by restart reconciliation."""

    repository: BaseTaskRepository

    def __init__(
        self,
        target: str,
        task_repository: str = "default",
        max_file_bytes: int = MAX_FILE_BYTES,
        max_archive_bytes: int = MAX_ARCHIVE_BYTES,
        max_archives_per_flush: int = MAX_ARCHIVES_PER_FLUSH,
        timeout_seconds: float = SYNC_TIMEOUT_SECONDS,
        task_names: Sequence[str] | None = None,
        **kwargs,
    ) -> None:
        removed = {"task_ids", "task_id_prefixes", "sync_on_start"} & kwargs.keys()
        if removed:
            raise ValueError(f"Removed sync options: {', '.join(sorted(removed))}; use task_names")
        super().__init__(**kwargs)
        if not isinstance(target, str) or not target.strip():
            raise ValueError("target must be a non-empty configured service address")
        if max_file_bytes <= 0:
            raise ValueError("max_file_bytes must be positive")
        if max_archive_bytes <= max_file_bytes:
            raise ValueError("max_archive_bytes must be larger than max_file_bytes")
        if max_archives_per_flush <= 0:
            raise ValueError("max_archives_per_flush must be positive")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.target = target.strip()
        self.depend("repository", task_repository, BaseTaskRepository)
        self.max_file_bytes = max_file_bytes
        self.max_archive_bytes = max_archive_bytes
        self.max_archives_per_flush = max_archives_per_flush
        self.timeout = timeout_seconds
        self.task_names = validate_task_names(task_names)
        self.root = self.workspace_path.expanduser().resolve()
        self.configured_target: TargetConfig | None = None
        self._pending: set[str] = set()
        self._flush_lock = asyncio.Lock()
        self._changes: TaskChangeSubscription | None = None
        self._change_consumer: asyncio.Task[None] | None = None

    def _client(self) -> HttpClient:
        configured = self.configured_target or self.app_config.resolve_target(self.target)
        return HttpClient(target=configured.address, timeout=self.timeout, token=configured.token)

    async def _reconcile(self) -> None:
        """Compare remote content first, then local terminal directories; never persist failures."""
        try:
            async with self._client() as client:
                response = await client.run_job("task_sync_index", {"task_names": sorted(self.task_names)})
            remote = response.answer
            if not response.success or not isinstance(remote, dict):
                raise ValueError(f"Remote sync index failed: {remote}")
            if any(not isinstance(key, str) or not isinstance(value, str) for key, value in remote.items()):
                raise ValueError("Remote sync index must map Task IDs to content digests")
            local = await asyncio.to_thread(snapshot_index, self.root, self.task_names)
            self._pending.update(task_id for task_id, digest in local.items() if remote.get(task_id) != digest)
            self.logger.info(f"Task sync reconciled target={self.target}: queued={len(self._pending)}")
        except Exception as exc:
            self.logger.warning(f"Task sync reconciliation skipped target={self.target}: {exc}; restart to repair")

    async def _start(self) -> None:
        self.configured_target = self.app_config.resolve_target(self.target)
        self._pending.clear()
        # Subscribe before scanning so changes during startup are retained.
        self._changes = self.repository.subscribe()
        await self._reconcile()
        self._change_consumer = asyncio.create_task(self._consume_changes(), name=f"axonx-sync:{self.name}")

    async def _close(self) -> None:
        if self._changes is not None:
            self._changes.close()
        if self._change_consumer is not None:
            self._change_consumer.cancel()
            with suppress(asyncio.CancelledError):
                await self._change_consumer
        self._changes = None
        self._change_consumer = None
        self._pending.clear()

    async def _consume_changes(self) -> None:
        assert self._changes is not None
        async for changes in self._changes:
            if changes.resync:
                # Recover missed watcher events using the same stateless comparison.
                await self._reconcile()
            self._pending.update(task_id for task_id in changes.task_ids if self._should_sync(task_id))

    def _should_sync(self, task_id: str) -> bool:
        return matches_task_name(task_id, self.task_names)

    def _settled(self, task_ids: Sequence[str]) -> list[str]:
        settled = []
        for task_id in task_ids:
            status = read_task_metadata(task_path(self.root, task_id), task_id)
            if status is not None and status.state.is_terminal:
                settled.append(task_id)
        return settled

    async def _send(self, client: HttpClient, archive: Path) -> None:
        staged: str | None = None
        try:
            digest = await asyncio.to_thread(file_sha256, archive)
            copied = await client.copy_file(archive, filename=SYNC_ARCHIVE_NAME)
            staged = copied.path
            if copied.sha256 != digest:
                raise ValueError("Remote workspace copy does not match the uploaded archive")
            response = await client.run_job("sync_tasks", {"path": staged})
            if not response.success:
                raise ValueError(f"Remote sync apply failed: {response.answer}")
        finally:
            if staged is not None:
                with suppress(Exception):
                    await client.discard_file(staged)

    def _plan(self, pending: Sequence[str]) -> dict[str, TaskPlan]:
        plans = {}
        for task_id in pending:
            try:
                plans[task_id] = plan_task(self.root, task_id, self.max_file_bytes)
            except OSError as exc:
                self.logger.warning(f"Task sync planning failed: {task_id}: {exc}; restart to repair")
        return plans

    async def _transfer(self, pending: Sequence[str]) -> SyncReport:
        plans = await asyncio.to_thread(self._plan, pending)
        batches, oversized, deferred = pack_batches(
            plans, archive_budget(self.max_archive_bytes), self.max_archives_per_flush
        )
        # Unattempted tasks remain queued; rejected/oversized tasks do not retry.
        self._pending.update(deferred)
        rejected = [f"{task_directory(task_id)}/{name}" for task_id, plan in plans.items() for name in plan.rejected]
        for task_id in oversized:
            self.logger.warning(f"Task sync snapshot exceeds limits or is incomplete: {task_id}; restart after repair")
        uploaded: list[str] = []
        if batches:
            async with self._client() as client:
                with tempfile.TemporaryDirectory(prefix="axonx-sync-") as staging:
                    archive = Path(staging) / SYNC_ARCHIVE_NAME
                    for batch in batches:
                        try:
                            included = await asyncio.to_thread(build_archive, plans, batch, archive)
                            if archive.stat().st_size > self.max_archive_bytes:
                                raise ValueError(f"Built sync archive exceeds {self.max_archive_bytes} bytes")
                            await self._send(client, archive)
                            uploaded.extend(included)
                        except Exception as exc:
                            self.logger.warning(f"Task sync batch failed target={self.target}: {batch}: {exc}")
        return SyncReport(
            uploaded=uploaded,
            rejected=rejected,
            oversized=[task_directory(task_id) for task_id in oversized],
            deferred=[task_directory(task_id) for task_id in deferred],
            archives=len(batches),
        )

    async def flush(self) -> SyncReport:
        """Send each queued terminal snapshot once, without retry or deletion propagation."""
        async with self._flush_lock:
            queued, self._pending = self._pending, set()
            if not queued:
                return SyncReport()
            pending = await asyncio.to_thread(self._settled, sorted(filter(self._should_sync, queued)))
            if not pending:
                return SyncReport()
            try:
                return await self._transfer(pending)
            except Exception as exc:
                self.logger.warning(f"Task sync flush failed target={self.target}: {exc}; restart to repair")
                return SyncReport()
