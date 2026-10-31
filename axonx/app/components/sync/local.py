"""Push newly selected or changed workflow views to one remote workspace."""

from __future__ import annotations

import asyncio
import math
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path

from ....client import http as client
from ....client.base import RemoteServiceError
from ....client.files import build_file_archive
from ....task.models.identity import validate_registration_name
from ....task.storage.logs import TaskLogReader
from ....task.storage.workspace import scan_entries, task_directory
from ....utils.async_work import run_blocking
from ..registry import provider
from .base import BaseSyncComponent
from .models import ReplicaBudgetError, SyncReport
from .replica import prepare_group


@provider("local")
class LocalSyncComponent(BaseSyncComponent):
    """Keep successful source versions locally; never reconcile remote state."""

    def __init__(
        self,
        target: str,
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
        if isinstance(model_names, str) or any(not isinstance(name, str) or not name for name in model_names):
            raise ValueError("model_names must be a sequence of nonempty patterns")
        self.target = target.strip()
        self.max_archives_per_flush = max_archives_per_flush
        self.timeout = timeout_seconds
        self.model_names = tuple(sorted(set(model_names)))
        self.rules = dict(rules or {})
        for task, when in self.rules.items():
            validate_registration_name(task)
            if when not in {"live", "terminal"}:
                raise ValueError("Sync rules must select 'live' or 'terminal'")
        self._sent: dict[str, str] = {}
        self._last_task = ""
        self._flush_lock = asyncio.Lock()

    def _client(self) -> client.HttpClient:
        configured = self.app_config.resolve_target(self.target)
        return client.HttpClient(target=configured.address, timeout=self.timeout, token=configured.token)

    async def _start(self) -> None:
        self.app_config.resolve_target(self.target)
        self._sent.clear()
        self._last_task = ""

    async def flush(self) -> SyncReport:
        async with self._flush_lock:
            return await self._flush()

    async def _flush(self) -> SyncReport:
        root = self.workspace.root
        roots = {
            identity: status
            for identity, status in (await run_blocking(scan_entries, root)).items()
            if status.replica is None and status.reg_name in self.rules
        }
        self._sent = {identity: version for identity, version in self._sent.items() if identity in roots}
        ordered = sorted(roots)
        ordered = [i for i in ordered if i > self._last_task] + [i for i in ordered if i <= self._last_task]
        report = SyncReport()
        budget = self.app_config.transfer_budget_bytes
        logs = TaskLogReader(root)
        if not roots:
            return report
        temporary = self.workspace.resolve("tmp/sync")
        temporary.mkdir(parents=True, exist_ok=True)
        async with self._client() as remote:
            for position, task_id in enumerate(ordered):
                if report.archives >= self.max_archives_per_flush:
                    report.deferred.extend(task_directory(identity) for identity in ordered[position:])
                    break
                when = self.rules[roots[task_id].reg_name]
                if when == "terminal" and not roots[task_id].state.is_terminal:
                    continue
                self._last_task = task_id
                try:
                    with tempfile.TemporaryDirectory(prefix="send-", dir=temporary) as directory:
                        staging = Path(directory)
                        prepared = await run_blocking(
                            prepare_group,
                            root,
                            task_id,
                            staging,
                            budget,
                            logs,
                            self._sent.get(task_id),
                            model_names=self.model_names,
                            when=when,
                        )
                        if prepared is None:
                            continue
                        version, plans = prepared
                        archive = staging / "files.tar.gz"
                        directories = {relative: plan.directory for relative, plan in plans.items()}
                        expanded_size = await run_blocking(build_file_archive, directories, archive)
                        if max(expanded_size, archive.stat().st_size) > budget:
                            raise ReplicaBudgetError("Archive exceeds the transfer budget")
                        report.archives += 1
                        uploaded = await remote.upload_archive(archive)
                        if set(uploaded) != plans.keys():
                            raise ValueError("Remote file transfer returned an incomplete directory list")
                        self._sent[task_id] = version
                        report.uploaded.extend(plans)
                except ReplicaBudgetError as exc:
                    report.rejected.append(task_directory(task_id))
                    self.logger.warning(f"Display push rejected {task_id}: {exc}")
                except (OSError, ValueError, RemoteServiceError) as exc:
                    report.deferred.append(task_directory(task_id))
                    self.logger.warning(f"Display push will retry {task_id}: {exc}")
        return report
