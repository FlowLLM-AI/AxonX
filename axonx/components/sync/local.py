"""Reconcile and transfer bounded terminal display replicas."""

from __future__ import annotations

import asyncio
import tempfile
from collections.abc import Sequence
from contextlib import suppress
from pathlib import Path

import httpx

from ...config import TargetConfig
from ...constants import DEFAULT_TRANSFER_BUDGET_BYTES
from ...task.storage.workspace import (
    read_task_metadata,
    scan_entries,
    task_directory,
    task_path,
)
from ...task.sync import (
    SYNC_ARCHIVE_NAME,
    SyncReport,
    archive_budget,
    build_archive,
    pack_batches,
)
from ...task.sync.errors import ReplicaBudgetError
from ...task.sync.index import (
    matches_task_name,
    policy_digest,
    snapshot_digest,
    validate_task_names,
)
from ...task.sync.replica import prepare_replica
from ...utils.async_work import run_blocking
from ...utils.fs import file_sha256
from ..client import HttpClient
from ..client.base import RemoteServiceError
from ..registry import provider
from ..task_repository import BaseTaskRepository, TaskChangeSubscription
from .base import BaseSyncComponent


@provider("local")
class LocalSyncComponent(BaseSyncComponent):
    repository: BaseTaskRepository

    def __init__(
        self,
        target: str,
        task_repository: str = "default",
        max_archives_per_flush: int = 4,
        timeout_seconds: float = 300,
        task_names: Sequence[str] | None = None,
        **kwargs,
    ) -> None:
        removed = {
            "task_ids",
            "task_id_prefixes",
            "sync_on_start",
            "max_file_bytes",
            "max_archive_bytes",
        } & kwargs.keys()
        if removed:
            raise ValueError(f"Removed sync options: {', '.join(sorted(removed))}")
        super().__init__(**kwargs)
        if not isinstance(target, str) or not target.strip():
            raise ValueError("target must be a non-empty configured service address")
        if max_archives_per_flush <= 0 or timeout_seconds <= 0:
            raise ValueError("max_archives_per_flush and timeout_seconds must be positive")
        self.target = target.strip()
        self.depend("repository", task_repository, BaseTaskRepository)
        self.max_archives_per_flush = max_archives_per_flush
        self.timeout = timeout_seconds
        self.task_names = validate_task_names(task_names)
        self.root = self.workspace_path.expanduser().resolve()
        self.configured_target: TargetConfig | None = None
        self._pending: set[str] = set()
        self._flush_lock = asyncio.Lock()
        self._changes: TaskChangeSubscription | None = None
        self._change_consumer: asyncio.Task[None] | None = None
        self._remote_budget: int | None = None
        self._needs_reconcile = True

    @property
    def budget(self) -> int:
        local = self.app_config.transfer_budget_bytes if self.app_context is not None else DEFAULT_TRANSFER_BUDGET_BYTES
        return min(local, self._remote_budget) if self._remote_budget is not None else local

    def _client(self) -> HttpClient:
        configured = self.configured_target or self.app_config.resolve_target(self.target)
        return HttpClient(target=configured.address, timeout=self.timeout, token=configured.token)

    def _missing(self, remote: dict) -> set[str]:
        policy = policy_digest(self.budget)
        missing = set()
        for task_id, metadata in scan_entries(self.root).items():
            if metadata.replica is not None or not metadata.state.is_terminal or not self._should_sync(task_id):
                continue
            try:
                expected = {
                    "source_digest": snapshot_digest(self.root, task_id),
                    "policy_digest": policy,
                }
                if remote.get(task_id) != expected:
                    missing.add(task_id)
            except (OSError, ValueError) as exc:
                self.logger.warning(f"Cannot index display source {task_id}: {exc}")
                missing.add(task_id)
        return missing

    async def _reconcile(self) -> None:
        self._needs_reconcile = False
        try:
            async with self._client() as client:
                response = await client.run_job("task_sync_index", {"task_names": sorted(self.task_names)})
            payload = response.answer
            if not response.success or not isinstance(payload, dict):
                raise ValueError("Remote display-replica index failed")
            budget, remote = payload.get("transfer_budget_bytes"), payload.get("tasks")
            if not isinstance(budget, int) or isinstance(budget, bool) or budget <= 0 or not isinstance(remote, dict):
                raise ValueError("Remote index must provide transfer_budget_bytes and tasks")
            if any(
                not isinstance(key, str)
                or not isinstance(value, dict)
                or set(value) != {"source_digest", "policy_digest"}
                or any(not isinstance(digest, str) or len(digest) != 64 for digest in value.values())
                for key, value in remote.items()
            ):
                raise ValueError("Invalid remote replica identities")
            self._remote_budget = budget
            self._pending.update(await run_blocking(self._missing, remote))
            self.logger.info(
                f"Display sync reconciled target={self.target}: queued={len(self._pending)} budget={self.budget}"
            )
        except asyncio.CancelledError:
            self._needs_reconcile = True
            raise
        except (OSError, ValueError, RemoteServiceError, httpx.HTTPError) as exc:
            self._needs_reconcile = True
            self.logger.warning(f"Display sync reconciliation will retry target={self.target}: {exc}")

    async def _start(self) -> None:
        self.configured_target = self.app_config.resolve_target(self.target)
        self._pending.clear()
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
                # The next flush owns reconciliation; there is one state mutation path.
                self._needs_reconcile = True
            self._pending.update(task_id for task_id in changes.task_ids if self._should_sync(task_id))

    def _should_sync(self, task_id: str) -> bool:
        return matches_task_name(task_id, self.task_names)

    def _settled(self, task_ids: Sequence[str]) -> list[str]:
        result = []
        for task_id in task_ids:
            metadata = read_task_metadata(task_path(self.root, task_id), task_id)
            if metadata is not None and metadata.state.is_terminal and metadata.replica is None:
                result.append(task_id)
        return result

    async def _send(self, client: HttpClient, archive: Path) -> None:
        staged = None
        try:
            digest = await run_blocking(file_sha256, archive)
            staged = f"tmp/{digest}/{SYNC_ARCHIVE_NAME}"
            copied = await client.copy_file(archive, filename=SYNC_ARCHIVE_NAME)
            staged = copied.path
            if copied.sha256 != digest:
                raise ValueError("Uploaded archive checksum mismatch")
            response = await client.run_job("sync_tasks", {"path": staged})
            if not response.success:
                raise ValueError(f"Remote replica commit failed: {response.answer}")
        finally:
            if staged is not None:
                with suppress(Exception):
                    await client.discard_file(staged)

    async def _transfer(self, pending: Sequence[str]) -> SyncReport:
        report = SyncReport()
        with tempfile.TemporaryDirectory(prefix="axonx-display-", dir=self.root) as temporary:
            staging = Path(temporary)
            plans = {}
            for task_id in pending:
                try:
                    plans[task_id] = await run_blocking(
                        prepare_replica,
                        self.root,
                        task_id,
                        task_path(staging, task_id),
                        self.budget,
                    )
                except (ReplicaBudgetError, ValueError) as exc:
                    report.rejected.append(task_directory(task_id))
                    self.logger.warning(f"Display sync rejected {task_id}: {exc}")
                except OSError as exc:
                    self._pending.add(task_id)
                    self.logger.warning(f"Display source will retry {task_id}: {exc}")
            batches, oversized, deferred = pack_batches(plans, archive_budget(self.budget), self.max_archives_per_flush)
            self._pending.update(deferred)
            report.oversized = [task_directory(task_id) for task_id in oversized]
            report.deferred = [task_directory(task_id) for task_id in deferred]
            if batches:
                async with self._client() as client:
                    for batch in batches:
                        report.archives += 1
                        try:
                            archive = staging / SYNC_ARCHIVE_NAME
                            included = await run_blocking(build_archive, plans, batch, archive)
                            if archive.stat().st_size > self.budget:
                                raise ReplicaBudgetError("Encoded archive exceeds transfer budget")
                            await self._send(client, archive)
                            report.uploaded.extend(included)
                        except (OSError, ValueError, RemoteServiceError, httpx.HTTPError) as exc:
                            self._pending.update(batch)
                            self.logger.warning(f"Display sync batch will retry target={self.target}: {batch}: {exc}")
        return report

    async def flush(self) -> SyncReport:
        async with self._flush_lock:
            if self._needs_reconcile:
                await self._reconcile()
                if self._needs_reconcile:
                    return SyncReport()
            queued, self._pending = self._pending, set()
            try:
                pending = await run_blocking(self._settled, sorted(filter(self._should_sync, queued)))
                if not pending:
                    return SyncReport()
                return await self._transfer(pending)
            except BaseException:
                self._pending.update(queued)
                raise
