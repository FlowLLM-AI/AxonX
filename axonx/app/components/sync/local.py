"""Reconcile and transfer bounded display replicas with opt-in live Task groups."""

from __future__ import annotations

import asyncio
import tempfile
from collections.abc import Callable, Sequence
from contextlib import suppress
from pathlib import Path

from ..client.base import RemoteServiceError
from ..client.http import HttpClient
from .base import BaseSyncComponent
from ..task_index.base import BaseTaskIndex
from ....common.async_work import run_blocking
from ....common.registry import provider
from ....task.models.lifecycle import DisplayReplica
from ....task.storage.logs import TaskLogReader
from ....task.storage.workspace import (
    read_task_metadata,
    scan_entries,
    task_directory,
    task_path,
)
from ....task.sync.archive import SYNC_ARCHIVE_NAME, build_archive
from ....task.sync.errors import ReplicaBudgetError
from ....task.sync.index import (
    matches_task_name,
    policy_revision,
    source_revision,
    validate_live_task_ids,
    validate_task_names,
)
from ....task.sync.models import SyncReport, TaskPlan
from ....task.sync.planner import archive_budget, pack_batches
from ....task.sync.replica import prepare_group, prepare_replica


@provider("local")
class LocalSyncComponent(BaseSyncComponent):
    index: BaseTaskIndex

    def __init__(
        self,
        target: str,
        task_index: str = "default",
        max_archives_per_flush: int = 4,
        timeout_seconds: float = 300,
        task_names: Sequence[str] | None = None,
        live_task_ids: Sequence[str] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        if self.kwargs:
            raise TypeError(f"Unexpected sync options: {', '.join(sorted(self.kwargs))}")
        if not isinstance(target, str) or not target.strip():
            raise ValueError("target must be a non-empty configured service address")
        if max_archives_per_flush <= 0 or timeout_seconds <= 0:
            raise ValueError("max_archives_per_flush and timeout_seconds must be positive")
        self.target = target.strip()
        self.depend("index", task_index, BaseTaskIndex)
        self.max_archives_per_flush = max_archives_per_flush
        self.timeout = timeout_seconds
        self.task_names = validate_task_names(task_names)
        self.live_task_ids = validate_live_task_ids(live_task_ids)
        self._remote_index: dict = {}
        self._last_task = ""
        self.root = self.workspace.root
        self._pending: set[str] = set()
        self._flush_lock = asyncio.Lock()
        self._unsubscribe: Callable[[], None] | None = None
        self._remote_budget: int | None = None
        self._needs_reconcile = True

    @property
    def budget(self) -> int:
        local = self.app_config.transfer_budget_bytes
        return min(local, self._remote_budget) if self._remote_budget is not None else local

    def _client(self) -> HttpClient:
        configured = self.app_config.resolve_target(self.target)
        return HttpClient(target=configured.address, timeout=self.timeout, token=configured.token)

    def _missing(self, remote: dict) -> set[str]:
        policy = policy_revision(self.budget)
        missing = set()
        members = self._group_members()
        for task_id, metadata in scan_entries(self.root).items():
            if (
                metadata.replica is not None
                or not metadata.state.is_terminal
                or not self._should_sync(task_id)
                or task_id in members
            ):
                continue
            try:
                expected = {
                    "source_revision": source_revision(self.root, task_id),
                    "policy_revision": policy,
                }
                if any(remote.get(task_id, {}).get(key) != value for key, value in expected.items()):
                    missing.add(task_id)
            except (OSError, ValueError) as exc:
                self.logger.warning(f"Cannot index display source {task_id}: {exc}")
                missing.add(task_id)
        return missing

    async def _reconcile(self, *, sources: bool = True) -> None:
        if sources:
            self._needs_reconcile = False
        try:
            async with self._client() as client:
                response = await client.run_job(
                    "task_sync_index",
                    {
                        "task_names": sorted(self.task_names),
                        "live_task_ids": sorted(self.live_task_ids),
                    },
                )
            payload = response.answer
            if not response.success or not isinstance(payload, dict):
                raise ValueError("Remote display-replica index failed")
            budget, remote = payload.get("transfer_budget_bytes"), payload.get("tasks")
            if not isinstance(budget, int) or isinstance(budget, bool) or budget <= 0 or not isinstance(remote, dict):
                raise ValueError("Remote index must provide transfer_budget_bytes and tasks")
            index = {}
            for identity, value in remote.items():
                if (
                    not isinstance(identity, str)
                    or not isinstance(value, dict)
                    or not isinstance(value.get("run_id"), str)
                ):
                    raise ValueError("Invalid remote replica identity")
                replica = DisplayReplica.model_validate({key: item for key, item in value.items() if key != "run_id"})
                index[identity] = {
                    "run_id": value["run_id"],
                    **replica.model_dump(mode="json"),
                }
            remote = index
            sources |= self._remote_budget is not None and self._remote_budget != budget
            self._remote_budget = budget
            self._remote_index = remote
            if sources:
                self._pending.update(await run_blocking(self._missing, remote))
            self.logger.info(
                f"Display sync reconciled target={self.target}: queued={len(self._pending)} budget={self.budget}"
            )
        except asyncio.CancelledError:
            self._needs_reconcile = True
            raise
        except (OSError, ValueError, RemoteServiceError) as exc:
            self._needs_reconcile = True
            self.logger.warning(f"Display sync reconciliation will retry target={self.target}: {exc}")

    async def _start(self) -> None:
        self.app_config.resolve_target(self.target)
        self._pending.clear()
        self._unsubscribe = self.index.subscribe(self._on_change)
        self._needs_reconcile = True

    async def _close(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        self._pending.clear()

    def _on_change(self, task_ids: frozenset[str]) -> None:
        self._pending.update(task_id for task_id in task_ids if self._should_sync(task_id))

    def _should_sync(self, task_id: str) -> bool:
        return matches_task_name(task_id, self.task_names)

    def _group_members(self) -> set[str]:
        """Reserve owned child directories even when their next Run is not created yet."""
        pending = list(self.live_task_ids)
        members = set()
        while pending:
            identity = pending.pop()
            if identity in members:
                continue
            members.add(identity)
            status = read_task_metadata(task_path(self.root, identity), identity)
            if status is not None and status.replica is None:
                pending.extend(child.task_id for child in status.children if child.task_id)
        return members

    def _settled(self, task_ids: Sequence[str]) -> list[str]:
        members = self._group_members()
        return [
            identity
            for identity in task_ids
            if (status := read_task_metadata(task_path(self.root, identity), identity)) is not None
            and status.replica is None
            and (
                identity in self.live_task_ids
                or status.state.is_terminal
                and identity not in members
                and self._should_sync(identity)
            )
        ]

    async def _send(self, client: HttpClient, archive: Path) -> None:
        staged = None
        try:
            copied = await client.copy_file(archive, filename=SYNC_ARCHIVE_NAME)
            staged = copied.path
            if copied.size != archive.stat().st_size:
                raise ValueError("Uploaded archive size mismatch")
            response = await client.run_job("sync_tasks", {"path": staged})
            if not response.success:
                raise ValueError(f"Remote replica commit failed: {response.answer}")
        finally:
            if staged is not None:
                with suppress(RemoteServiceError):
                    await client.discard_file(staged)

    def _pack(self, groups):
        sizes = {
            identity: TaskPlan(
                tuple(f for plan in members.values() for f in plan.files),
                sum(plan.size for plan in members.values()),
            )
            for identity, members in groups.items()
        }
        return pack_batches(
            sizes,
            archive_budget(self.budget),
            self.max_archives_per_flush,
            members={identity: set(members) for identity, members in groups.items()},
        )

    async def _transfer(self, pending: Sequence[str]) -> SyncReport:
        report = SyncReport()
        ordered = sorted(pending)
        ordered = [i for i in ordered if i > self._last_task] + [i for i in ordered if i <= self._last_task]
        with tempfile.TemporaryDirectory(prefix="axonx-display-", dir=self.root) as temporary:
            staging = Path(temporary)
            groups = {}
            for position, task_id in enumerate(ordered):
                try:
                    group_root = staging / task_id
                    if task_id in self.live_task_ids:
                        plans = await run_blocking(
                            prepare_group,
                            self.root,
                            task_id,
                            group_root,
                            self.budget,
                            TaskLogReader(Path(self.app_config.log_dir)),
                            self._remote_index,
                        )
                    else:
                        plan = await run_blocking(
                            prepare_replica,
                            self.root,
                            task_id,
                            task_path(group_root, task_id),
                            self.budget,
                            TaskLogReader(Path(self.app_config.log_dir)),
                        )
                        plans = {task_id: plan}
                    if plans:
                        groups[task_id] = plans
                        _, _, deferred = self._pack(groups)
                        if deferred:
                            remaining = ordered[position + 1 :]
                            self._pending.update(remaining)
                            report.deferred.extend(task_directory(identity) for identity in remaining)
                            break
                except ReplicaBudgetError as exc:
                    report.rejected.append(task_directory(task_id))
                    self.logger.warning(f"Display sync rejected {task_id}: {exc}")
                except (OSError, ValueError) as exc:
                    self._pending.add(task_id)
                    report.deferred.append(task_directory(task_id))
                    self.logger.warning(f"Display source will retry {task_id}: {exc}")
            batches, oversized, deferred = self._pack(groups)
            self._pending.update(deferred)
            report.oversized = [task_directory(identity) for identity in oversized]
            report.deferred.extend(task_directory(identity) for identity in deferred)
            if batches:
                async with self._client() as client:
                    for batch in batches:
                        self._last_task = batch[-1]
                        report.archives += 1
                        try:
                            plans = {identity: plan for group in batch for identity, plan in groups[group].items()}
                            archive = staging / SYNC_ARCHIVE_NAME
                            included = await run_blocking(build_archive, plans, list(plans), archive)
                            if archive.stat().st_size > self.budget:
                                raise ReplicaBudgetError("Encoded archive exceeds transfer budget")
                            await self._send(client, archive)
                            report.uploaded.extend(included)
                        except (OSError, ValueError, RemoteServiceError) as exc:
                            self._pending.update(batch)
                            report.deferred.extend(task_directory(identity) for identity in batch)
                            self.logger.warning(f"Display sync batch will retry target={self.target}: {batch}: {exc}")
        return report

    async def flush(self) -> SyncReport:
        async with self._flush_lock:
            # Active and completed replicas share one index, queue, budget and sender.
            if self._needs_reconcile or self.live_task_ids:
                await self._reconcile(sources=self._needs_reconcile)
                if self._needs_reconcile:
                    return SyncReport(deferred=[task_directory(i) for i in sorted(self.live_task_ids)])
            queued, self._pending = self._pending | self.live_task_ids, set()
            try:
                pending = await run_blocking(self._settled, sorted(queued))
                return await self._transfer(pending) if pending else SyncReport()
            except BaseException:
                self._pending.update(queued)
                raise
