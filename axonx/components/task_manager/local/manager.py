"""Local Task manager facade."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
import os
from pathlib import Path

from ..base import BaseTaskManager
from ...registry import R
from ....constants import (
    AXONX_SERVICE_INFO,
    AXONX_TASK_LOG_DIR,
    AXONX_TASK_STATUS_MIN_INTERVAL,
    AXONX_TASK_WORKSPACE_DIR,
)
from ....schema import TaskStatus
from ....task.arguments import task_name_from_argv
from .logs import TaskLogLocator
from .process import TaskProcessSupervisor
from .reconciliation import TaskStateReconciler, WorkerExit
from .repository import TaskStatusRepository


@R.register("local")
class LocalTaskManager(BaseTaskManager):
    """Coordinate local worker processes and durable Task status snapshots."""

    def __init__(self, version: int = 1, terminate_grace_seconds: float = 5, **kwargs):
        super().__init__(**kwargs)
        self.version = version
        self._statuses: dict[str, TaskStatus] = {}
        self._status_lock = asyncio.Lock()
        self._repository = TaskStatusRepository(self.workspace_path, version)
        self._logs = TaskLogLocator(Path(self.app_config.log_dir))
        self._reconciler = TaskStateReconciler()
        self._supervisor = TaskProcessSupervisor(
            terminate_grace_seconds,
            self.logger,
            self._handle_worker_exit,
        )

    @property
    def task_manager_dir(self) -> Path:
        """Return the directory containing task-manager state."""
        return self._repository.directory

    @property
    def status_path(self) -> Path:
        """Return the persisted task-status file path."""
        return self._repository.path

    @property
    def log_dir(self) -> Path:
        """Return the process-log directory shared with Task workers."""
        return self._logs.log_dir

    @property
    def _processes(self):
        return self._supervisor.processes

    @property
    def _process_monitors(self):
        return self._supervisor.monitors

    async def _start(self) -> None:
        if os.name != "posix":
            raise NotImplementedError("LocalTaskManager supports macOS and Linux")
        try:
            loaded = await asyncio.to_thread(self._repository.load)
            if loaded is None:
                return
            self._statuses = loaded.statuses
            if loaded.foreign_workspace is not None:
                self.logger.warning(f"Ignoring task history copied from workspace {loaded.foreign_workspace}")
            else:
                await asyncio.to_thread(self._logs.prepare_loaded, self._statuses)
                for status in self._statuses.values():
                    self._reconciler.restore(status)
            if loaded.should_save:
                await self._save()
        except Exception as exc:  # noqa
            self._statuses = {}
            self.logger.error(
                f"Failed to load task status from {self.status_path}: {type(exc).__name__}: {exc}; "
                "starting with empty history",
            )

    async def _close(self) -> None:
        try:
            terminated = await self._supervisor.shutdown()
            async with self._status_lock:
                self._reconciler.cancel_pids(self._statuses, terminated)
        finally:
            async with self._status_lock:
                await self._save()

    async def submit(self, argv: Sequence[str]) -> None:
        if not self.is_started:
            raise RuntimeError("Task manager is not running")
        if isinstance(argv, (str, bytes)) or not all(isinstance(value, str) for value in argv):
            raise TypeError("Task arguments must be a sequence of strings")
        environment = dict(self.app_config.environment)
        environment[AXONX_TASK_WORKSPACE_DIR] = str(self.workspace_path.resolve())
        environment[AXONX_TASK_LOG_DIR] = str(self.log_dir)
        if service_info := os.environ.get(AXONX_SERVICE_INFO):
            environment[AXONX_SERVICE_INFO] = service_info
        status_interval = os.environ.get(AXONX_TASK_STATUS_MIN_INTERVAL)
        if status_interval is not None:
            environment.setdefault(AXONX_TASK_STATUS_MIN_INTERVAL, status_interval)
        await self._supervisor.spawn(argv, environment, task_name_from_argv(argv) or "unknown")

    async def set_status(self, task_id: str, status: TaskStatus) -> None:
        if task_id != status.task_id:
            raise ValueError("Task status ID does not match task_id")
        async with self._status_lock:
            snapshot = self._reconciler.accept(task_id, self._statuses.get(task_id), status)
            if snapshot is None:
                return
            await asyncio.to_thread(self._logs.attach, snapshot)
            self._statuses[task_id] = snapshot
            await self._save()

    async def list_runtime_task_ids(self) -> list[str]:
        async with self._status_lock:
            return sorted(self._statuses)

    async def list_runtime_task_statuses(self) -> list[TaskStatus]:
        async with self._status_lock:
            await asyncio.to_thread(self._logs.attach_all, self._statuses)
            return [self._statuses[task_id].model_copy(deep=True) for task_id in sorted(self._statuses, reverse=True)]

    async def get_status(self, task_id: str) -> TaskStatus:
        async with self._status_lock:
            status = self._statuses[task_id]
            await asyncio.to_thread(self._logs.attach, status)
            return status.model_copy(deep=True)

    async def cancel(self, task_id: str) -> bool:
        async with self._status_lock:
            status = self._statuses[task_id]
            if status.pid is None or status.state.is_terminal or not await self._supervisor.cancel(status.pid):
                return False
            self._reconciler.cancel(status)
            await self._save()
            return True

    async def delete(self, task_ids: Sequence[str]) -> list[str]:
        if isinstance(task_ids, (str, bytes)) or not all(isinstance(task_id, str) for task_id in task_ids):
            raise TypeError("task_ids must be a sequence of strings")
        async with self._status_lock:
            deleted = []
            for task_id in dict.fromkeys(task_ids):
                status = self._statuses.get(task_id)
                if status is not None and status.state.is_terminal:
                    del self._statuses[task_id]
                    self._reconciler.mark_deleted(task_id)
                    deleted.append(task_id)
            if deleted:
                await self._save()
            return deleted

    async def _handle_worker_exit(self, worker_exit: WorkerExit) -> None:
        async with self._status_lock:
            if self._reconciler.record_exit(self._statuses, worker_exit):
                await self._save()

    async def _save(self) -> None:
        await asyncio.to_thread(self._repository.save, tuple(self._statuses.values()))
