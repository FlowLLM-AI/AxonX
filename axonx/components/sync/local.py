"""Replicate queued task-directory changes to a remote node."""

from __future__ import annotations

import asyncio
import tempfile
from collections.abc import Sequence
from contextlib import suppress
from pathlib import Path

from ...config import RemoteNode
from ...constants import MAX_ARCHIVE_BYTES
from ...task.storage.workspace import read_status, task_directory, task_path
from ...task.sync import (
    SYNC_ARCHIVE_NAME,
    SyncReport,
    TaskPlan,
    archive_budget,
    build_archive,
    pack_batches,
    plan_task,
)
from ...utils.fs import file_sha256
from ..client import HttpClient
from ..registry import provider
from ..task_repository import BaseTaskRepository, TaskChangeSubscription
from .base import BaseSyncComponent
from .state import SyncStateStore

MAX_FILE_BYTES = 100 * 1024 * 1024
MAX_ARCHIVES_PER_FLUSH = 4
SYNC_TIMEOUT_SECONDS = 300.0


@provider("local")
class LocalSyncComponent(BaseSyncComponent):
    """Replicate workspace task directories to a configured remote AxonX node.

    Change detection comes from the shared Task repository. Calling :meth:`flush` is a
    separate policy, normally owned by a scheduled Job.
    """

    repository: BaseTaskRepository

    def __init__(
        self,
        remote_ip: str,
        task_repository: str = "default",
        max_file_bytes: int = MAX_FILE_BYTES,
        max_archive_bytes: int = MAX_ARCHIVE_BYTES,
        max_archives_per_flush: int = MAX_ARCHIVES_PER_FLUSH,
        timeout_seconds: float = SYNC_TIMEOUT_SECONDS,
        sync_on_start: bool = True,
        task_ids: Sequence[str] | None = None,
        task_id_prefixes: Sequence[str] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        if not isinstance(remote_ip, str) or not remote_ip.strip():
            raise ValueError(
                "remote_ip must be a non-empty address of a configured remote node"
            )
        if max_file_bytes <= 0:
            raise ValueError("max_file_bytes must be positive")
        if max_archive_bytes <= max_file_bytes:
            raise ValueError("max_archive_bytes must be larger than max_file_bytes")
        if max_archives_per_flush <= 0:
            raise ValueError("max_archives_per_flush must be positive")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.remote_ip = remote_ip.strip()
        self.depend("repository", task_repository, BaseTaskRepository)
        self.max_file_bytes = max_file_bytes
        self.max_archive_bytes = max_archive_bytes
        self.max_archives_per_flush = max_archives_per_flush
        self.timeout = timeout_seconds
        self.sync_on_start = sync_on_start
        if isinstance(task_ids, str) or isinstance(task_id_prefixes, str):
            raise ValueError("Task filters must be lists of strings")
        self.task_ids = frozenset(task_ids or ())
        self.task_id_prefixes = tuple(task_id_prefixes or ())
        if any(
            not isinstance(value, str) or not value
            for value in (*self.task_ids, *self.task_id_prefixes)
        ):
            raise ValueError("Task filters must contain non-empty strings")
        self.root = self.workspace_path.expanduser().resolve()
        self._state = SyncStateStore(self.root, self.remote_ip)
        self.node: RemoteNode | None = None
        self._pending: set[str] = set()
        self._acknowledged: set[str] = set()
        self._resync = False
        self._change_lock = asyncio.Lock()
        self._flush_lock = asyncio.Lock()
        self._changes: TaskChangeSubscription | None = None
        self._change_consumer: asyncio.Task[None] | None = None

    async def _start(self) -> None:
        # Resolve the target once so a misconfigured address fails startup rather
        # than every flush.
        self.node = self.app_config.resolve_remote_node(self.remote_ip)
        self._changes = self.repository.subscribe()
        self._change_consumer = asyncio.create_task(
            self._consume_changes(), name="axonx-sync-queue"
        )
        self._acknowledged = await asyncio.to_thread(self._state.load)
        current = set((await self.repository.entries()).keys())
        if self.sync_on_start and current:
            # A restart replays the whole workspace rather than assuming the target
            # still holds what it held last time.
            self.logger.info(
                f"Workspace sync queued its whole workspace: tasks={len(current)}"
            )
            await self._requeue(current)

    async def _close(self) -> None:
        if self._changes is not None:
            self._changes.close()
            self._changes = None
        if self._change_consumer is not None:
            self._change_consumer.cancel()
            with suppress(asyncio.CancelledError):
                await self._change_consumer
            self._change_consumer = None

    async def _consume_changes(self) -> None:
        """Coalesce repository batches into the next scheduled flush."""
        assert self._changes is not None
        async for changes in self._changes:
            async with self._change_lock:
                self._pending.update(changes.task_ids)
                self._resync |= changes.resync

    async def _take_changed(self) -> tuple[set[str], bool]:
        """Drain the queue and report whether the repository missed a watch window."""
        async with self._change_lock:
            taken, self._pending = self._pending, set()
            resync, self._resync = self._resync, False
            return taken, resync

    async def _requeue(self, task_ids: Sequence[str]) -> None:
        async with self._change_lock:
            self._pending.update(task_ids)

    def _should_sync(self, task_id: str) -> bool:
        return not (self.task_ids or self.task_id_prefixes) or (
            task_id in self.task_ids or task_id.startswith(self.task_id_prefixes)
        )

    def _plan(self, task_ids: Sequence[str]) -> dict[str, TaskPlan]:
        return {
            task_id: plan_task(self.root, task_id, self.max_file_bytes)
            for task_id in task_ids
        }

    def _is_settled(self, task_id: str) -> bool:
        """Whether a task has stopped writing, so its files are safe to ship whole.

        A receiver must never infer liveness from a process ID owned by another
        machine, so synchronization publishes only terminal snapshots.
        """
        directory = task_path(self.root, task_id)
        status = read_status(directory, task_id)
        return status is not None and status.state.is_terminal

    def _settled(self, task_ids: Sequence[str]) -> list[str]:
        return [task_id for task_id in task_ids if self._is_settled(task_id)]

    async def _send(self, target: Path | None, deletions: Sequence[str]) -> None:
        """Upload one archive for the receiver to apply, and report removals."""
        node = self.node or self.app_config.resolve_remote_node(self.remote_ip)
        async with HttpClient(
            host_ip=node.host_ip,
            host_port=node.host_port,
            timeout=self.timeout,
            token=node.token,
        ) as client:
            staged: str | None = None
            try:
                if target is not None:
                    digest = await asyncio.to_thread(file_sha256, target)
                    copied = await client.copy_file(target, filename=SYNC_ARCHIVE_NAME)
                    staged = copied.path
                    # The receiver recomputes the digest of what actually arrived.
                    if copied.sha256 != digest:
                        raise ValueError(
                            "Remote workspace copy does not match the uploaded archive"
                        )
                response = await client.run_job(
                    "sync_tasks",
                    {"path": staged, "deletions": list(deletions)},
                )
            finally:
                if staged is not None:
                    with suppress(Exception):
                        await client.discard_file(staged)
        # A step that reports failure still answers with HTTP 200, so the payload
        # is what decides, not the status code.
        if not response.success:
            raise ValueError(f"Remote sync apply failed: {response.answer}")

    async def _transfer(
        self, pending: Sequence[str], removed: Sequence[str]
    ) -> SyncReport:
        plans = await asyncio.to_thread(self._plan, pending)
        batches, oversized, deferred = pack_batches(
            plans,
            archive_budget(self.max_archive_bytes),
            self.max_archives_per_flush,
        )
        # Every plan is reported, not just the ones that reached an archive: a task
        # whose files are all too large never gets a batch, and dropping it without
        # a word is what the report and these warnings exist to prevent.
        rejected = [
            f"{task_directory(task_id)}/{name}"
            for task_id, plan in plans.items()
            for name in plan.rejected
        ]
        uploaded: list[str] = []
        delivered = False
        if batches:
            with tempfile.TemporaryDirectory(prefix="axonx-sync-") as staging:
                target = Path(staging) / SYNC_ARCHIVE_NAME
                for index, batch in enumerate(batches):
                    included = await asyncio.to_thread(
                        build_archive, plans, batch, target
                    )
                    if target.stat().st_size > self.max_archive_bytes:
                        raise ValueError(
                            f"Built sync archive exceeds {self.max_archive_bytes} bytes"
                        )
                    # Deletions ride along with the first archive so they are reported
                    # even when the removed tasks were the only thing that changed.
                    await self._send(target, removed if index == 0 else [])
                    delivered = True
                    uploaded.extend(included)
        elif removed:
            # Nothing to upload, but the receiver still has to drop what went away.
            # Nothing is deferred either: a deferral always comes with a batch.
            await self._send(None, removed)
            delivered = True
        if deferred:
            # Nothing was sent for these, so they have to come back next interval.
            await self._requeue(deferred)
        if oversized:
            await self._requeue(oversized)
        if rejected:
            self.logger.warning(
                f"Rejecting incomplete Task snapshots: files={', '.join(rejected)}"
            )
        for task_id in oversized:
            self.logger.warning(
                f"Skipping a task that cannot be replicated within the size limits: task={task_directory(task_id)}",
            )
        return SyncReport(
            uploaded=uploaded,
            deleted=list(removed) if delivered else [],
            rejected=rejected,
            oversized=[task_directory(task_id) for task_id in oversized],
            deferred=[task_directory(task_id) for task_id in deferred],
            archives=len(batches),
        )

    async def flush(self) -> SyncReport:
        """Replicate the changes queued since the last flush."""
        async with self._flush_lock:
            queued, resync = await self._take_changed()
            current = set((await self.repository.entries()).keys())
            if resync:
                # The watcher missed a window, so the whole workspace is re-examined
                # rather than only what it managed to report.
                self.logger.warning(
                    "Task repository watcher was down; re-examining the whole workspace"
                )
                queued |= current
            # The receiver names task directories by their kind and ID together.
            removed = sorted(
                task_directory(task_id)
                for task_id in self._acknowledged - current
                if self._should_sync(task_id)
            )
            pending = sorted(filter(self._should_sync, queued & current))
            if pending:
                settled = set(await asyncio.to_thread(self._settled, pending))
                # A task that is still writing goes back in the queue rather than out
                # of it, so it is picked up as soon as it finishes.
                await self._requeue(
                    [task_id for task_id in pending if task_id not in settled]
                )
                pending = [task_id for task_id in pending if task_id in settled]
            if not pending and not removed:
                return SyncReport()
            try:
                result = await self._transfer(pending, removed)
            except BaseException:
                # The batch was already drained, so a failed round must put it back
                # rather than wait for the files to change again.
                await self._requeue(pending)
                raise
            uploaded_ids = {path.split("/", 1)[1] for path in result.uploaded}
            deleted_ids = {path.split("/", 1)[1] for path in result.deleted}
            self._acknowledged.difference_update(deleted_ids)
            self._acknowledged.update(uploaded_ids)
            await asyncio.to_thread(self._state.save, self._acknowledged)
            return result
