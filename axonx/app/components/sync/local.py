"""Reconcile workflow views through one queue, snapshot builder and sender."""

from __future__ import annotations

import asyncio
import math
import tempfile
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from pathlib import Path

from ....client import http as client
from ....client.base import RemoteServiceError
from ....task.models.identity import validate_registration_name
from ....task.models.lifecycle import DisplayReplica
from ....task.storage.logs import TaskLogReader
from ....task.storage.workspace import (
    read_task_metadata,
    scan_entries,
    task_directory,
    task_path,
)
from ....utils.async_work import run_blocking
from ..registry import provider
from ..task_index.base import BaseTaskIndex
from .archive import SYNC_ARCHIVE_NAME, archive_budget, build_archive, pack_batches
from .base import BaseSyncComponent
from .models import ReplicaBudgetError, SyncReport, TaskPlan
from .replica import prepare_group


@provider("local")
class LocalSyncComponent(BaseSyncComponent):
    index: BaseTaskIndex

    def __init__(
        self,
        target: str,
        task_index: str = "default",
        max_archives_per_flush: int = 4,
        timeout_seconds: float = 300,
        model_names: Sequence[str] = (),
        rules: Mapping[str, str] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        if self.kwargs:
            raise TypeError(f"Unexpected sync options: {', '.join(sorted(self.kwargs))}")
        if not isinstance(target, str) or not target.strip():
            raise ValueError("target must be a non-empty configured service address")
        if (
            isinstance(max_archives_per_flush, bool)
            or not isinstance(max_archives_per_flush, int)
            or max_archives_per_flush <= 0
        ):
            raise ValueError("max_archives_per_flush must be a positive integer")
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be finite and positive")
        self.target = target.strip()
        self.depend("index", task_index, BaseTaskIndex)
        self.max_archives_per_flush = max_archives_per_flush
        self.timeout = timeout_seconds
        if isinstance(model_names, str) or any(not isinstance(name, str) or not name for name in model_names):
            raise ValueError("model_names must be a sequence of nonempty patterns")
        self.model_names = tuple(sorted(set(model_names)))
        self.rules = dict(rules or {})
        for task, when in self.rules.items():
            validate_registration_name(task)
            if when not in {"live", "terminal"}:
                raise ValueError("Sync rules must select 'live' or 'terminal'")
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

    def _client(self) -> client.HttpClient:
        configured = self.app_config.resolve_target(self.target)
        return client.HttpClient(target=configured.address, timeout=self.timeout, token=configured.token)

    def _roots(self) -> dict:
        return {
            identity: status
            for identity, status in scan_entries(self.root).items()
            if status.replica is None and status.reg_name in self.rules
        }

    async def _reconcile(self, roots: dict) -> bool:
        sources = self._needs_reconcile
        try:
            async with self._client() as remote:
                response = await remote.run_job(
                    "task_sync_index",
                    {
                        "root_task_ids": sorted(roots),
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
                    or not isinstance(value.get("started_at"), str)
                ):
                    raise ValueError("Invalid remote replica identity")
                replica = DisplayReplica.model_validate(
                    {key: item for key, item in value.items() if key != "started_at"}
                )
                index[identity] = {
                    "started_at": value["started_at"],
                    **replica.model_dump(mode="json"),
                }
            remote = index
            sources |= self._remote_budget is not None and self._remote_budget != budget
            self._remote_budget = budget
            self._remote_index = remote
            self._pending.update(
                identity
                for identity, status in roots.items()
                if sources or remote.get(identity, {}).get("started_at") != status.started_at.isoformat()
            )
            self._needs_reconcile = False
            self.logger.info(
                f"Display sync reconciled target={self.target}: queued={len(self._pending)} budget={self.budget}"
            )
            return True
        except asyncio.CancelledError:
            self._needs_reconcile = True
            raise
        except (OSError, ValueError, RemoteServiceError) as exc:
            self._needs_reconcile = True
            self.logger.warning(f"Display sync reconciliation will retry target={self.target}: {exc}")
            return False

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
        for identity in task_ids:
            seen = set()
            while identity and identity not in seen:
                seen.add(identity)
                status = read_task_metadata(task_path(self.root, identity), identity)
                if status is None or status.replica is not None:
                    break
                if status.reg_name in self.rules:
                    self._pending.add(identity)
                    break
                identity = status.parent_task_id

    async def _send(self, remote: client.HttpClient, archive: Path) -> None:
        staged = None
        try:
            copied = await remote.copy_file(archive, filename=SYNC_ARCHIVE_NAME)
            staged = copied.path
            if copied.size != archive.stat().st_size:
                raise ValueError("Uploaded archive size mismatch")
            response = await remote.run_job("sync_tasks", {"path": staged})
            if not response.success:
                raise ValueError(f"Remote replica commit failed: {response.answer}")
        finally:
            if staged is not None:
                with suppress(RemoteServiceError):
                    await remote.discard_file(staged)

    def _pack(self, groups: dict[str, dict[str, TaskPlan]]) -> tuple[list[list[str]], list[str], list[str]]:
        return pack_batches(
            groups,
            archive_budget(self.budget),
            self.max_archives_per_flush,
        )

    async def _transfer(self, pending: Sequence[str], roots: dict) -> SyncReport:
        report = SyncReport()
        logs = TaskLogReader(self.root)
        ordered = sorted(pending)
        ordered = [i for i in ordered if i > self._last_task] + [i for i in ordered if i <= self._last_task]
        temporary_root = self.workspace.resolve("tmp/sync")
        temporary_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="send-", dir=temporary_root) as temporary:
            staging = Path(temporary)
            groups = {}
            for position, task_id in enumerate(ordered):
                try:
                    group_root = staging / task_id
                    plans = await run_blocking(
                        prepare_group,
                        self.root,
                        task_id,
                        group_root,
                        self.budget,
                        logs,
                        self._remote_index,
                        model_names=self.model_names,
                        when=self.rules[roots[task_id].reg_name],
                    )
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
                async with self._client() as remote:
                    for batch in batches:
                        self._last_task = batch[-1]
                        report.archives += 1
                        try:
                            plans = {identity: plan for group in batch for identity, plan in groups[group].items()}
                            archive = staging / SYNC_ARCHIVE_NAME
                            included = await run_blocking(build_archive, plans, archive)
                            if archive.stat().st_size > self.budget:
                                raise ReplicaBudgetError("Encoded archive exceeds transfer budget")
                            await self._send(remote, archive)
                            report.uploaded.extend(included)
                        except (OSError, ValueError, RemoteServiceError) as exc:
                            self._pending.update(batch)
                            report.deferred.extend(task_directory(identity) for identity in batch)
                            self.logger.warning(f"Display sync batch will retry target={self.target}: {batch}: {exc}")
        return report

    async def flush(self) -> SyncReport:
        async with self._flush_lock:
            roots = await run_blocking(self._roots)
            self._pending.intersection_update(roots)
            if not roots:
                return SyncReport()
            if not await self._reconcile(roots):
                return SyncReport(deferred=[task_directory(identity) for identity in sorted(roots)])
            self._pending.update(
                identity for identity, status in roots.items() if self.rules[status.reg_name] == "live"
            )
            ready = {
                identity
                for identity in self._pending
                if self.rules[roots[identity].reg_name] == "live" or roots[identity].state.is_terminal
            }
            self._pending.difference_update(ready)
            try:
                return await self._transfer(sorted(ready), roots) if ready else SyncReport()
            except BaseException:
                self._pending.update(ready)
                raise
