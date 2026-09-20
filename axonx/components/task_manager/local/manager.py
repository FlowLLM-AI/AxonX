"""Run local task workers and answer queries from the workspace they write to."""

from __future__ import annotations

import asyncio
import os
from collections import Counter
from collections.abc import AsyncIterator, Sequence
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from ....cli.parser import parse_command
from ....components.job.base import JobEvent
from ....constants import (
    AXONX_TASK_CREATED_AT,
    AXONX_TASK_ID,
    AXONX_TASK_LOG_DIR,
    AXONX_TASK_RUN_ID,
    AXONX_TASK_TIMEZONE,
    AXONX_TASK_WORKSPACE_DIR,
    CLI_EXEC_COMMAND,
    CLI_RAW_ARGUMENTS,
)
from ....enums import TaskState
from ....task.catalog import resolve_task
from ....task.contracts import TaskHandle
from ....task.query import (
    TaskGraph,
    TaskGraphList,
    graph_summaries,
    stream_task,
    task_graph,
)
from ....task.runtime.arguments import build_task_argv, split_task_arguments
from ....task.storage.events import LOG_WINDOW_BYTES, TaskLogChunk
from ....task.storage.logs import TaskLogReader
from ....task.storage.workspace import (
    TaskStatus,
    is_task_directory,
    read_entry,
    task_path,
)
from ...registry import provider
from ...task_repository import BaseTaskRepository
from ..base import BaseTaskManager
from .supervisor import TaskProcessSupervisor, WorkerExit, pid_alive

# The stderr tail one failure message carries: enough for a traceback's last
# frames, bounded so a chatty worker cannot bloat the status file a UI reads.
ERROR_TAIL_CHARS = 2_048


@provider("local")
class LocalTaskManager(BaseTaskManager):
    """Run local workers and answer queries from the workspace they write to."""

    repository: BaseTaskRepository

    def __init__(
        self,
        task_repository: str = "default",
        terminate_grace_seconds: float = 5,
        reaper_interval_seconds: float = 5,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        if reaper_interval_seconds <= 0:
            raise ValueError("reaper_interval_seconds must be positive")
        self.depend("repository", task_repository, BaseTaskRepository)
        self._logs = TaskLogReader(Path(self.app_config.log_dir).expanduser().resolve())
        self._lock = asyncio.Lock()
        self._reaper: asyncio.Task | None = None
        self._reaper_interval = reaper_interval_seconds
        self._supervisor = TaskProcessSupervisor(
            terminate_grace_seconds, self.logger, self._handle_worker_exit
        )

    async def _start(self) -> None:
        if os.name != "posix":
            raise NotImplementedError("LocalTaskManager supports macOS and Linux")
        await self._repair_dead_tasks(repair_queued=True)
        self._reaper = asyncio.create_task(
            self._reap_periodically(), name="axonx-task-reaper"
        )

    async def _close(self) -> None:
        if self._reaper is not None:
            self._reaper.cancel()
            with suppress(asyncio.CancelledError):
                await self._reaper
            self._reaper = None
        terminated = await self._supervisor.shutdown()
        for entry in (await self.repository.entries()).values():
            status = entry.status
            if (
                status is not None
                and status.run_id in terminated
                and not status.state.is_terminal
            ):
                await self._finish(
                    status, TaskState.CANCELLED, 130, "Task manager stopped"
                )

    async def submit(self, argv: Sequence[str]) -> TaskHandle:
        if not self.is_started:
            raise RuntimeError("Task manager is not running")
        if isinstance(argv, (str, bytes)):
            raise TypeError("Task arguments must be a sequence of strings")
        argv = tuple(argv)
        if not all(isinstance(value, str) for value in argv):
            raise TypeError("Task arguments must be a sequence of strings")
        command, _ = parse_command((CLI_EXEC_COMMAND, *argv))
        arguments = {
            key: value
            for key, value in command.arguments.items()
            if key != CLI_RAW_ARGUMENTS
        }
        task_name, config = split_task_arguments(arguments)
        run_id = uuid4().hex
        task = resolve_task(task_name)(
            config,
            workspace_path=self.workspace_path,
            reg_name=task_name,
            timezone=self.app_config.timezone,
            run_id=run_id,
        )
        directory = task_path(self.workspace_path, task.task_id)
        if directory.parent.is_symlink():
            raise ValueError(
                f"Task type directory cannot be a symlink: {directory.parent}"
            )
        directory.mkdir(parents=True, exist_ok=False)
        status = TaskStatus(
            task_id=task.task_id,
            run_id=run_id,
            task_type=task.task_type,
            task_name=task_name,
            config=task.input_params.model_dump(mode="json"),
            state=TaskState.QUEUED,
            created_at=task.created_at,
        )
        await self.repository.put_status(status)
        worker_argv = build_task_argv(
            task_name,
            task.input_params.model_dump(mode="json"),
        )
        handed_over = {
            AXONX_TASK_WORKSPACE_DIR: str(self.workspace_path.resolve()),
            AXONX_TASK_LOG_DIR: str(self._logs.directory),
            AXONX_TASK_TIMEZONE: self.app_config.timezone,
            AXONX_TASK_ID: task.task_id,
            AXONX_TASK_RUN_ID: run_id,
            AXONX_TASK_CREATED_AT: task.created_at.isoformat(),
        }
        try:
            await self._supervisor.spawn(
                worker_argv,
                {**self.app_config.environment, **handed_over},
                task.task_id,
                task_name,
                run_id,
            )
        except BaseException as exc:
            await self._finish(
                status, TaskState.FAILED, 1, f"Worker could not start: {exc}"
            )
            raise
        return TaskHandle(task.task_id, run_id, task_name)

    async def list_statuses(self) -> list[TaskStatus]:
        statuses = [
            status.model_copy(deep=True)
            for status in (await self.repository.statuses()).values()
        ]
        statuses.sort(
            key=lambda status: (
                status.created_at.timestamp()
                if status.created_at is not None
                else float("-inf"),
                status.task_id,
            ),
            reverse=True,
        )
        return statuses

    async def get_status(self, task_id: str) -> TaskStatus:
        return (await self._status_of(task_id)).model_copy(deep=True)

    async def list_graphs(
        self, query: str = "", offset: int = 0, limit: int = 50
    ) -> TaskGraphList:
        return graph_summaries(await self.repository.records(), query, offset, limit)

    async def get_graph(self, task_id: str) -> TaskGraph:
        return task_graph(await self.repository.records(), task_id)

    async def read_log(
        self, task_id: str, offset: int = -1, limit: int = LOG_WINDOW_BYTES
    ) -> TaskLogChunk:
        return await asyncio.to_thread(
            self._logs.read,
            self._logs.path(await self._status_of(task_id)),
            offset,
            limit,
        )

    async def stream(
        self, task_id: str, poll_interval: float = 0.5
    ) -> AsyncIterator[JobEvent]:
        """Replay one Task's progress and log until it reaches a terminal state."""
        async for event in stream_task(
            self.workspace_path,
            self._logs,
            self._status_of,
            self.logger,
            task_id,
            poll_interval,
        ):
            yield event

    async def cancel(self, task_id: str) -> bool:
        async with self._lock:
            status = (await self.repository.entry(task_id)).status
            if status is None or status.state.is_terminal:
                return False
            if not await self._supervisor.cancel_run(status.run_id):
                return False
            await self._finish(status, TaskState.CANCELLED, 130, "Task cancelled")
            return True

    async def delete(self, task_ids: Sequence[str]) -> list[str]:
        if isinstance(task_ids, (str, bytes)) or not all(
            isinstance(task_id, str) for task_id in task_ids
        ):
            raise TypeError("task_ids must be a sequence of strings")
        deleted = []
        async with self._lock:
            entries = await self.repository.entries()
            # Count how many tasks still reference each log before anything is removed.
            logs = Counter(self._logs.path(entry.status) for entry in entries.values())
            for task_id in dict.fromkeys(task_ids):
                try:
                    directory = task_path(self.workspace_path, task_id)
                except ValueError:
                    continue
                entry = entries.get(task_id)
                if (
                    entry is None
                    or directory.is_symlink()
                    or directory.parent.is_symlink()
                ):
                    continue
                status = entry.status
                if status is not None and (
                    not status.state.is_terminal
                    or self._supervisor.is_managed_run(status.run_id)
                ):
                    continue
                if not await self.repository.delete_terminal(task_id):
                    continue
                log_path = self._logs.path(status)
                if logs[log_path] == 1 and self._logs.is_task_log(log_path):
                    await asyncio.to_thread(log_path.unlink, missing_ok=True)
                logs[log_path] -= 1
                deleted.append(task_id)
        return deleted

    async def _status_of(self, task_id: str) -> TaskStatus:
        """Return a task's status as the index holds it; raise KeyError when it has none."""
        status = (await self.repository.entry(task_id)).status
        if status is None:
            raise KeyError(task_id)
        return status

    async def _write_status(self, status: TaskStatus) -> None:
        """Persist one status this manager decided and index it, ahead of the watcher."""
        directory = task_path(self.workspace_path, status.task_id)
        if not is_task_directory(directory):
            # A delete won the race, and writing would recreate the directory it removed.
            return
        await self.repository.put_status(status)

    async def _finish(
        self, status: TaskStatus, state: TaskState, code: int, error: str
    ) -> None:
        status = status.model_copy(deep=True)
        status.state = state
        status.finished_at = datetime.now(UTC)
        status.exit_code = code
        status.error = error
        await self._write_status(status)

    async def _reap_periodically(self) -> None:
        while True:
            await asyncio.sleep(self._reaper_interval)
            try:
                await self._repair_dead_tasks()
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger.exception(
                    "Failed to repair dead Tasks; retrying on the next interval"
                )

    async def _repair_dead_tasks(self, *, repair_queued: bool = False) -> None:
        """Fail every task whose worker died without reporting an outcome itself."""
        for task_id, entry in (await self.repository.entries()).items():
            status = entry.status
            orphaned = status is not None and (
                status.state == TaskState.RUNNING
                and not pid_alive(status.pid)
                or repair_queued
                and status.state == TaskState.QUEUED
            )
            if orphaned:
                await self._settle_dead_task(
                    task_id, 1, "Task process ended without a final status"
                )

    async def _handle_worker_exit(self, worker_exit: WorkerExit) -> None:
        """Report the outcome of a worker this process launched and watched exit."""
        error = f"Worker exited without final status (code {worker_exit.return_code})"
        if worker_exit.stderr_tail:
            error += f": {worker_exit.stderr_tail[-ERROR_TAIL_CHARS:]}"
        code = min(255, abs(worker_exit.return_code)) or 1
        try:
            status = (await self.repository.entry(worker_exit.task_id)).status
        except KeyError:
            return
        if (
            status is not None
            and status.run_id == worker_exit.run_id
            and not status.state.is_terminal
        ):
            await self._settle_dead_task(worker_exit.task_id, code, error, gone=True)

    async def _settle_dead_task(
        self, task_id: str, code: int, error: str, *, gone: bool = False
    ) -> None:
        """Write the outcome of a task whose worker is gone.

        The task directory decides, not the index: a worker writes its own final
        status and only then exits, and the watcher may not have reported that write
        yet — a cached entry that still says ``running`` is not evidence that the
        worker died mid-flight. So the directory is read again, and what it says
        replaces the cached entry rather than being overwritten by it.

        ``gone`` names how the caller knows the worker left: true when it watched the
        process exit, and false when it only inferred that from a status whose process
        ID no longer answers. Only the inferred case confirms it against the file, for
        the sake of a task replicated from another node: that status carries a foreign
        process ID, and a process this machine happens to find alive under it is not
        the worker that wrote it.
        """
        async with self._lock:
            entry = await asyncio.to_thread(read_entry, self.workspace_path, task_id)
            if entry is None or entry.status is None:
                await self.repository.forget(task_id)
                return
            if entry.status.state.is_terminal or (
                not gone and pid_alive(entry.status.pid)
            ):
                await self.repository.put_status(entry.status)
                return
            await self._finish(entry.status, TaskState.FAILED, code, error)
