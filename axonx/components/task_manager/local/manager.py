"""Local task processes and their workspace-backed index."""

from __future__ import annotations

import asyncio
import os
import shutil
from collections.abc import Sequence
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

from ..base import BaseTaskManager
from ..types import TaskGraph, TaskGraphList, TaskLogChunk
from ...registry import R
from ....constants import AXONX_TASK_LOG_DIR, AXONX_TASK_TIMEZONE, AXONX_TASK_WORKSPACE_DIR
from ....enums import TaskState
from ....schema import TaskStatus
from ....task.arguments import task_name_from_argv
from ....utils.fs import atomic_write_json
from .index import TaskIndex
from .process import TaskProcessSupervisor, WorkerExit


@R.register("local")
class LocalTaskManager(BaseTaskManager):
    """Run local workers and query their on-disk task records."""

    def __init__(self, terminate_grace_seconds: float = 5, **kwargs):
        super().__init__(**kwargs)
        self._index = TaskIndex(self.workspace_path, self.logger)
        self._log_dir = Path(self.app_config.log_dir).expanduser().resolve()
        self._lock = asyncio.Lock()
        self._reaper: asyncio.Task | None = None
        self._supervisor = TaskProcessSupervisor(terminate_grace_seconds, self.logger, self._handle_worker_exit)

    async def _start(self) -> None:
        if os.name != "posix":
            raise NotImplementedError("LocalTaskManager supports macOS and Linux")
        await self._index.start()
        await self._mark_dead_tasks()
        self._reaper = asyncio.create_task(self._repair_dead_tasks(), name="axonx-task-reaper")

    async def _close(self) -> None:
        if self._reaper is not None:
            self._reaper.cancel()
            with suppress(asyncio.CancelledError):
                await self._reaper
            self._reaper = None
        try:
            terminated = await self._supervisor.shutdown()
            for record in (await self._index.snapshot()).values():
                status = record.status
                if status is not None and status.pid in terminated and not status.state.is_terminal:
                    await self._finish(status, TaskState.CANCELLED, 130, "Task manager stopped")
        finally:
            await self._index.close()

    @staticmethod
    def _pid_alive(pid: int | None) -> bool:
        if pid is None or pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    async def _repair_dead_tasks(self) -> None:
        while True:
            await asyncio.sleep(5)
            await self._mark_dead_tasks()

    async def _mark_dead_tasks(self) -> None:
        async with self._lock:
            for task_id, record in (await self._index.snapshot()).items():
                status = record.status
                if status is None or status.state.is_terminal or self._pid_alive(status.pid):
                    continue
                try:
                    current = (await self._index.get(task_id)).status
                except KeyError:
                    continue
                if current is not None and not current.state.is_terminal and not self._pid_alive(current.pid):
                    await self._finish(current, TaskState.FAILED, 1, "Task process ended without a final status")

    async def submit(self, argv: Sequence[str]) -> None:
        if not self.is_started:
            raise RuntimeError("Task manager is not running")
        if isinstance(argv, (str, bytes)) or not all(isinstance(value, str) for value in argv):
            raise TypeError("Task arguments must be a sequence of strings")
        environment = dict(self.app_config.environment)
        environment[AXONX_TASK_WORKSPACE_DIR] = str(self.workspace_path.resolve())
        environment[AXONX_TASK_LOG_DIR] = str(self._log_dir)
        environment[AXONX_TASK_TIMEZONE] = self.app_config.timezone
        await self._supervisor.spawn(argv, environment, task_name_from_argv(argv) or "unknown")

    async def list_ids(self) -> list[str]:
        return sorted(task_id for task_id, record in (await self._index.snapshot()).items() if record.status is not None)

    async def list_statuses(self) -> list[TaskStatus]:
        records = await self._index.snapshot()
        return [record.status.model_copy(deep=True) for _, record in sorted(records.items(), reverse=True) if record.status is not None]

    async def get_status(self, task_id: str) -> TaskStatus:
        status = (await self._index.get(task_id)).status
        if status is None:
            raise KeyError(task_id)
        return status.model_copy(deep=True)

    async def list_graphs(self, query: str = "", offset: int = 0, limit: int = 50) -> TaskGraphList:
        return await self._index.list_graphs(query, offset, limit)

    async def get_graph(self, task_id: str) -> TaskGraph:
        return await self._index.get_graph(task_id)

    async def read_log(self, task_id: str, offset: int = -1, limit: int = 65_536) -> TaskLogChunk:
        if offset < -1 or limit <= 0:
            raise ValueError("Invalid task log range")
        status = await self.get_status(task_id)
        if not status.log_path:
            return {
                "content": "", "start_offset": 0, "next_offset": 0, "file_size": 0,
                "has_more_before": False, "has_more_after": False, "reset": False,
            }
        path = Path(status.log_path).expanduser().resolve()
        if not path.is_relative_to(self._log_dir) or path.suffix != ".log":
            raise ValueError("Task log path is outside the configured log directory")
        if not path.is_file():
            raise FileNotFoundError(f"Task log does not exist: {path.name}")
        file_size = path.stat().st_size
        reset = offset > file_size
        start_offset = max(0, file_size - limit) if offset < 0 or reset else offset
        with path.open("rb") as file:
            file.seek(start_offset)
            data = file.read(limit)
        next_offset = start_offset + len(data)
        return {
            "content": data.decode("utf-8", errors="replace"),
            "start_offset": start_offset, "next_offset": next_offset, "file_size": file_size,
            "has_more_before": start_offset > 0, "has_more_after": next_offset < file_size,
            "reset": reset,
        }

    async def cancel(self, task_id: str) -> bool:
        async with self._lock:
            record = await self._index.get(task_id)
            status = record.status
            if status is None or status.pid is None or status.state.is_terminal:
                return False
            if not await self._supervisor.cancel(status.pid):
                return False
            await self._finish(status, TaskState.CANCELLED, 130, "Task cancelled")
            return True

    async def delete(self, task_ids: Sequence[str]) -> list[str]:
        if isinstance(task_ids, (str, bytes)) or not all(isinstance(task_id, str) for task_id in task_ids):
            raise TypeError("task_ids must be a sequence of strings")
        deleted = []
        async with self._lock:
            records = await self._index.snapshot()
            for task_id in dict.fromkeys(task_ids):
                try:
                    path = self._index.path(task_id)
                except ValueError:
                    continue
                record = records.get(task_id)
                if record is None or path.is_symlink() or path.parent.is_symlink():
                    continue
                status = record.status
                if status is None and record.metadata is None:
                    continue
                if status is not None and not status.state.is_terminal:
                    continue
                if status is not None and status.pid in self._supervisor.processes:
                    continue
                log_path = Path(status.log_path).expanduser().resolve() if status and status.log_path else None
                await asyncio.to_thread(shutil.rmtree, path)
                records.pop(task_id)
                await self._index.remove(task_id)
                other_logs = {Path(other.status.log_path).expanduser().resolve() for other in records.values() if other.status and other.status.log_path}
                if log_path is not None and log_path not in other_logs and log_path.suffix == ".log" and log_path.is_relative_to(self._log_dir):
                    await asyncio.to_thread(log_path.unlink, missing_ok=True)
                deleted.append(task_id)
        return deleted

    async def _write_status(self, status: TaskStatus) -> None:
        path = self._index.path(status.task_id) / "status.json"
        if path.parent.is_symlink() or path.parent.parent.is_symlink() or not path.parent.is_dir():
            return
        await asyncio.to_thread(atomic_write_json, path, status.model_dump(mode="json"))
        await self._index.put_status(status)

    async def _finish(self, status: TaskStatus, state: TaskState, code: int, error: str) -> None:
        status = status.model_copy(deep=True)
        status.state = state
        status.finished_at = datetime.now(UTC)
        status.exit_code = code
        status.error = error
        await self._write_status(status)

    async def _handle_worker_exit(self, worker_exit: WorkerExit) -> None:
        async with self._lock:
            for record in (await self._index.snapshot()).values():
                status = record.status
                if status is not None and status.pid == worker_exit.pid and not status.state.is_terminal:
                    code = min(255, abs(worker_exit.return_code)) or 1
                    error = f"Worker exited without final status (code {worker_exit.return_code})"
                    if worker_exit.stderr_tail:
                        error += f": {worker_exit.stderr_tail[-2048:]}"
                    await self._finish(status, TaskState.FAILED, code, error)
