"""Run local task workers and answer queries from the workspace they write to."""

from __future__ import annotations

import asyncio
import os
from collections import Counter
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from ....components.job.events import JobEvent
from ....constants import (
    AXONX_TASK_CREATED_AT,
    AXONX_TASK_ID,
    AXONX_TASK_LOG_DIR,
    AXONX_TASK_RUN_ID,
    AXONX_TASK_TIMEZONE,
    AXONX_TASK_WORKSPACE_DIR,
)
from ....task.protocol import PROTOCOL_VERSION
from ....task.source import TASK_SOURCE, TASK_SOURCE_ENV
from ....enums import TaskState
from ....plugin_kit.environment import environment_operation, run_in_thread, serialized
from ....task.catalog import resolve_task
from ....task.contracts import TaskHandle
from ....task.core import BaseTask
from ....task.query import (
    TaskGraph,
    stream_task,
    task_graph,
)
from ....task.query.summary import task_sort_key
from ....task.runtime.arguments import build_task_argv, parse_task_argv
from ....task.storage.composition import settle_children
from ....progress import settle_steps
from ....task.storage.events import (
    LOG_WINDOW_BYTES,
    TaskLogChunk,
    append_progress_snapshots,
)
from ....task.storage.logs import TaskLogReader
from ....task.storage.workspace import (
    EVENTS_FILE,
    TaskMetadata,
    is_task_directory,
    read_entry,
    read_task_metadata,
    task_path,
)
from ...registry import provider
from ...task_repository import BaseTaskRepository
from ..base import BaseTaskManager
from .supervisor import TaskProcessSupervisor, WorkerExit

# The stderr tail one failure message carries: enough for a traceback's last
# frames, bounded so a chatty worker cannot bloat the lifecycle record a UI reads.
ERROR_TAIL_CHARS = 2_048


@provider("local")
class LocalTaskManager(BaseTaskManager):
    """Run local workers and answer queries from the workspace they write to."""

    repository: BaseTaskRepository

    def __init__(
        self,
        task_repository: str = "default",
        terminate_grace_seconds: float = 5,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.depend("repository", task_repository, BaseTaskRepository)
        self._logs = TaskLogReader(Path(self.app_config.log_dir).expanduser().resolve())
        self._lock = asyncio.Lock()
        self._supervisor = TaskProcessSupervisor(terminate_grace_seconds, self.logger, self._handle_worker_exit)

    async def _start(self) -> None:
        if os.name != "posix":
            raise NotImplementedError("LocalTaskManager supports macOS and Linux")

    async def _close(self) -> None:
        terminated = await self._supervisor.shutdown()
        for status in (await self.repository.entries()).values():
            if status.run_id in terminated and not status.state.is_terminal:
                await self._finish(status, TaskState.CANCELLED, 130, "Task manager stopped")

    @environment_operation
    async def submit(self, argv: Sequence[str]) -> TaskHandle:
        if not self.is_started:
            raise RuntimeError("Task manager is not running")
        if isinstance(argv, (str, bytes)):
            raise TypeError("Task arguments must be a sequence of strings")
        argv = tuple(argv)
        if not all(isinstance(value, str) for value in argv):
            raise TypeError("Task arguments must be a sequence of strings")
        registration_name, config = parse_task_argv(argv)
        run_id = uuid4().hex
        for _ in range(100):
            task = await run_in_thread(self._prepare_task, registration_name, config, run_id)
            async with self._lock:
                if not await self._reserve(task, not task.is_generated_name):
                    continue
                status = TaskMetadata(
                    version=PROTOCOL_VERSION,
                    task_id=task.task_id,
                    run_id=run_id,
                    task_type=task.task_type,
                    reg_name=registration_name,
                    source=TASK_SOURCE.get(),
                    report_kind=task.report_kind,
                    input_params=task.input_params.model_dump(mode="json"),
                    state=TaskState.QUEUED,
                    created_at=task.created_at,
                )
                await self.repository.put_metadata(status)
            break
        else:
            raise RuntimeError("Could not allocate a unique Task name")

        worker_argv = build_task_argv(
            registration_name,
            task.input_params.model_dump(mode="json"),
        )
        handed_over = {
            AXONX_TASK_WORKSPACE_DIR: str(self.workspace_path.resolve()),
            AXONX_TASK_LOG_DIR: str(self._logs.directory),
            AXONX_TASK_TIMEZONE: self.app_config.timezone,
            AXONX_TASK_ID: task.task_id,
            AXONX_TASK_RUN_ID: run_id,
            TASK_SOURCE_ENV: status.source.model_dump_json(),
            AXONX_TASK_CREATED_AT: task.created_at.isoformat(),
        }
        try:
            await self._supervisor.spawn(
                worker_argv,
                {**self.app_config.environment, **handed_over},
                task.task_id,
                registration_name,
                run_id,
            )
        except BaseException as exc:
            await self._finish(status, TaskState.FAILED, 1, f"Worker could not start: {exc}")
            raise
        return TaskHandle(task.task_id, run_id, registration_name)

    @serialized
    def _prepare_task(self, registration_name: str, config: dict, run_id: str) -> BaseTask:
        """Resolve and validate with the same installed plugin generation."""
        return resolve_task(registration_name)(
            config,
            workspace_path=self.workspace_path,
            reg_name=registration_name,
            timezone=self.app_config.timezone,
            run_id=run_id,
            source=TASK_SOURCE.get(),
        )

    async def _reserve(self, task: BaseTask, replace: bool) -> bool:
        """Claim a Task directory, replacing only a completed named Task."""
        directory = task_path(self.workspace_path, task.task_id)
        if directory.parent.is_symlink():
            raise ValueError(f"Task type directory cannot be a symlink: {directory.parent}")
        try:
            directory.mkdir(parents=True, exist_ok=False)
            return True
        except FileExistsError:
            if not replace:
                return False

        status = await asyncio.to_thread(read_entry, self.workspace_path, task.task_id)
        if status is not None and status.replica is not None:
            raise ValueError("Display replicas are read-only; execute on the source service")
        if status is None or not status.state.is_terminal:
            raise FileExistsError(f"Active Task already exists: {task.task_id}")

        log_path = self._logs.path(status)
        if not await self.repository.reset_terminal(task.task_id):
            raise FileExistsError(f"Task cannot be replaced: {task.task_id}")

        remaining = await self.repository.entries()
        if self._logs.is_task_log(log_path) and all(self._logs.path(item) != log_path for item in remaining.values()):
            await asyncio.to_thread(log_path.unlink, missing_ok=True)
        return True

    async def list_statuses(self) -> list[TaskMetadata]:
        return sorted((await self.repository.entries()).values(), key=task_sort_key, reverse=True)

    async def list_managed_run_ids(self) -> list[str]:
        """Include tracked workers even when metadata has finished or been replaced."""
        return list(self._supervisor.run_pids)

    async def list_summaries(self) -> list[dict]:
        return await self.repository.summaries()

    async def get_status(self, task_id: str) -> TaskMetadata:
        return await self._status_of(task_id)

    async def get_graph(self, task_id: str) -> TaskGraph:
        return task_graph(await self.repository.entries(), task_id)

    async def read_log(
        self,
        task_id: str,
        offset: int = -1,
        limit: int = LOG_WINDOW_BYTES,
        *,
        run_id: str | None = None,
    ) -> TaskLogChunk:
        status = await self._status_of(task_id)
        if run_id is not None and status.run_id != run_id:
            raise ValueError(f"Task run changed: {task_id}")
        return await asyncio.to_thread(
            self._logs.read_status,
            self.workspace_path,
            status,
            offset,
            limit,
        )

    # Async generators satisfy the base contract returning an AsyncIterator.
    async def stream(  # pylint: disable=invalid-overridden-method
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

    async def cancel(self, task_id: str | None = None, run_id: str | None = None) -> bool:
        if task_id is None and run_id is None:
            raise ValueError("Cancellation requires task_id or run_id")
        for name, value in (("task_id", task_id), ("run_id", run_id)):
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} must be a non-empty string")
        async with self._lock:
            if task_id is not None:
                try:
                    status = await self.repository.entry(task_id)
                except KeyError:
                    status = None
                if status is None or (run_id is not None and status.run_id != run_id):
                    return False
                run_id = status.run_id
            else:
                status = next(
                    (item for item in (await self.repository.entries()).values() if item.run_id == run_id),
                    None,
                )
            assert run_id is not None
            if status is not None and status.replica is not None:
                raise ValueError("Display replicas are read-only; cancel on the source service")
            if status is not None and not status.state.is_terminal and not self._supervisor.is_managed_run(run_id):
                raise RuntimeError(f"Cannot confirm termination of unmanaged Run: {status.task_id} {run_id}")
            # Supervisor identity is immutable even if the named Task has been replaced.
            cancelled = await self._supervisor.cancel_run(run_id)
            if cancelled and status is not None and not status.state.is_terminal:
                await self._finish(status, TaskState.CANCELLED, 130, "Task cancelled")
            return cancelled

    async def delete(self, task_ids: Sequence[str]) -> list[str]:
        if isinstance(task_ids, (str, bytes)) or not all(isinstance(task_id, str) for task_id in task_ids):
            raise TypeError("task_ids must be a sequence of strings")
        deleted = []
        async with self._lock:
            entries = await self.repository.entries()
            # Count how many tasks still reference each log before anything is removed.
            logs = Counter(self._logs.path(entry) for entry in entries.values())
            for task_id in dict.fromkeys(task_ids):
                try:
                    directory = task_path(self.workspace_path, task_id)
                except ValueError:
                    continue
                entry = entries.get(task_id)
                if entry is None or directory.is_symlink() or directory.parent.is_symlink():
                    continue
                status = entry
                if not status.state.is_terminal or self._supervisor.is_managed_run(status.run_id):
                    continue
                if not await self.repository.delete_terminal(task_id):
                    continue
                log_path = self._logs.path(status)
                if logs[log_path] == 1 and self._logs.is_task_log(log_path):
                    await asyncio.to_thread(log_path.unlink, missing_ok=True)
                logs[log_path] -= 1
                deleted.append(task_id)
        return deleted

    async def _status_of(self, task_id: str) -> TaskMetadata:
        """Return a task's status as the index holds it; raise KeyError when it has none."""
        return await self.repository.entry(task_id)

    async def _write_task_metadata(self, status: TaskMetadata) -> None:
        """Persist one status this manager decided and index it, ahead of the watcher."""
        directory = task_path(self.workspace_path, status.task_id)
        if not is_task_directory(directory, strict_io=True):
            # A delete won the race, and writing would recreate the directory it removed.
            return
        await self.repository.put_metadata(status)

    async def _finish(self, status: TaskMetadata, state: TaskState, code: int, error: str) -> None:
        current = await asyncio.to_thread(
            read_task_metadata,
            task_path(self.workspace_path, status.task_id),
            status.task_id,
            strict_io=True,
        )
        if current is None or current.run_id != status.run_id:
            await self.repository.reconcile()
            return
        status = current
        if state in {TaskState.FAILED, TaskState.CANCELLED}:
            children = await asyncio.to_thread(settle_children, self.workspace_path, status, state, code, error)
            for child in children:
                await asyncio.to_thread(
                    append_progress_snapshots,
                    task_path(self.workspace_path, child.task_id) / EVENTS_FILE,
                    child.steps,
                )
                await self._write_task_metadata(child)
        status.state = state
        status.finished_at = datetime.now(UTC)
        settle_steps(
            status.steps,
            failed=state != TaskState.SUCCEEDED,
            error=error,
            now=status.finished_at,
        )
        status.exit_code = code
        status.error = error
        await asyncio.to_thread(
            append_progress_snapshots,
            task_path(self.workspace_path, status.task_id) / EVENTS_FILE,
            status.steps,
        )
        await self._write_task_metadata(status)

    async def _handle_worker_exit(self, worker_exit: WorkerExit) -> None:
        """Fail an owned Run only after observing its worker exit without a final status.

        Other machines may share this workspace. Read the current on-disk Run
        before writing so a stale index or an old worker cannot replace its result.
        """
        error = f"Worker exited without final status (code {worker_exit.return_code})"
        if worker_exit.stderr_tail:
            error += f": {worker_exit.stderr_tail[-ERROR_TAIL_CHARS:]}"
        code = min(255, abs(worker_exit.return_code)) or 1
        async with self._lock:
            status = await asyncio.to_thread(
                read_task_metadata,
                task_path(self.workspace_path, worker_exit.task_id),
                worker_exit.task_id,
                strict_io=True,
            )
            if status is not None and status.run_id == worker_exit.run_id and not status.state.is_terminal:
                await self._finish(status, TaskState.FAILED, code, error)
            else:
                # Refresh the index without rewriting a worker's result or a replacement Run.
                await self.repository.reconcile()
