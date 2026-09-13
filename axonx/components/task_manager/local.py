"""Launch local task workers and store externally reported status."""

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import signal
import sys
from typing import Any

from .base import BaseTaskManager
from ..registry import R
from ...constants import AXONX_SERVICE_INFO, AXONX_TASK_WORKSPACE_DIR
from ...enums import TaskState
from ...schema import TaskStatus
from ...task.arguments import task_name_from_argv


@R.register("local")
class LocalTaskManager(BaseTaskManager):
    """Launch local workers, monitor their exits, and store reported status."""

    def __init__(self, version: int = 1, terminate_grace_seconds: float = 5, **kwargs):
        super().__init__(**kwargs)
        if terminate_grace_seconds < 0:
            raise ValueError("terminate_grace_seconds must not be negative")
        self.version = version
        self.terminate_grace_seconds = terminate_grace_seconds
        self._statuses: dict[str, TaskStatus] = {}
        self._processes: dict[int, asyncio.subprocess.Process] = {}
        self._process_monitors: set[asyncio.Task[None]] = set()
        self._shutdown_processes: set[int] = set()
        self._abnormal_exits: dict[int, tuple[int, str, datetime]] = {}
        self._deleted_task_ids: set[str] = set()

    @property
    def task_manager_dir(self) -> Path:
        """Return the directory containing task-manager state."""
        directory = self.workspace_path.resolve() / "task_manager"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @property
    def status_path(self) -> Path:
        """Return the persisted task-status file path."""
        return self.task_manager_dir / "status.json"

    @property
    def log_dir(self) -> Path:
        """Return the process-log directory shared with Task workers."""
        return Path(os.environ.get("AXONX_LOG_DIR") or "logs").expanduser().resolve()

    def _attach_log_path(self, status: TaskStatus) -> None:
        """Backfill legacy statuses by matching the worker PID in log filenames."""
        if status.log_path or status.pid is None or not self.log_dir.is_dir():
            return
        matches = tuple(self.log_dir.glob(f"*_{status.pid}.log"))
        if matches:
            status.log_path = str(max(matches, key=lambda path: path.stat().st_mtime))

    def _save_status(self):
        payload = {
            "version": self.version,
            "tasks": [
                status.model_dump(mode="json") for status in self._statuses.values()
            ],
        }
        temporary = self.status_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False),
            encoding="utf-8",
        )
        temporary.replace(self.status_path)

    async def _start(self):
        if os.name != "posix":
            raise NotImplementedError("LocalTaskManager supports macOS and Linux")
        if self.status_path.is_file():
            try:
                data = json.loads(self.status_path.read_text(encoding="utf-8"))
                if data.get("version") == self.version:
                    statuses = (
                        TaskStatus.model_validate(status)
                        for status in data.get("tasks", [])
                    )
                    self._statuses = {status.task_id: status for status in statuses}
                    for status in self._statuses.values():
                        self._attach_log_path(status)
            except Exception as exc:  # noqa
                self._statuses = {}
                self.logger.error(
                    f"Failed to load task status from {self.status_path}: {type(exc).__name__}: {exc}; "
                    "starting with empty history",
                )

    async def _close(self):
        try:
            await self._terminate_processes()
        finally:
            self._save_status()

    async def _terminate_processes(self) -> None:
        """Terminate and reap every worker process launched by this manager."""
        processes = tuple(
            process
            for process in self._processes.values()
            if process.returncode is None
        )
        if not processes:
            return

        self._shutdown_processes.update(process.pid for process in processes)
        terminated = {
            process.pid
            for process in processes
            if self._signal(process.pid, signal.SIGTERM)
        }
        monitors = tuple(self._process_monitors)
        if monitors and self.terminate_grace_seconds > 0:
            await asyncio.wait(monitors, timeout=self.terminate_grace_seconds)

        survivors = tuple(
            process for process in processes if process.returncode is None
        )
        for process in survivors:
            if self._signal(process.pid, signal.SIGKILL):
                terminated.add(process.pid)

        if monitors:
            _, pending = await asyncio.wait(
                monitors,
                timeout=max(1, self.terminate_grace_seconds),
            )
            for monitor in pending:
                monitor.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

        now = datetime.now(UTC)
        for status in self._statuses.values():
            if status.pid in terminated and not status.state.is_terminal:
                status.state = TaskState.CANCELLED
                status.finished_at = now
                status.exit_code = 130

    async def submit(self, argv: Sequence[str]) -> None:
        if not self.is_started:
            raise RuntimeError("Task manager is not running")
        if isinstance(argv, (str, bytes)) or not all(
            isinstance(value, str) for value in argv
        ):
            raise TypeError("Task arguments must be a sequence of strings")
        environment = dict(self.app_config.environment)
        environment[AXONX_TASK_WORKSPACE_DIR] = str(self.workspace_path.resolve())
        if service_info := os.environ.get(AXONX_SERVICE_INFO):
            environment[AXONX_SERVICE_INFO] = service_info
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "axonx.cli",
            "exec",
            *argv,
            env=environment,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        self._processes[process.pid] = process
        monitor = asyncio.create_task(
            self._monitor_process(process, self._task_name(argv)),
            name=f"axonx-task-monitor-{process.pid}",
        )
        self._process_monitors.add(monitor)
        monitor.add_done_callback(self._process_monitors.discard)

    async def _monitor_process(self, process: Any, task_name: str) -> None:
        """Relay worker stderr and report a non-zero process exit asynchronously."""
        stderr_tail = bytearray()
        tail_limit = 32 * 1024
        try:
            if process.stderr is not None:
                while chunk := await process.stderr.read(8192):
                    sys.stderr.write(chunk.decode(errors="replace"))
                    sys.stderr.flush()
                    stderr_tail.extend(chunk)
                    if len(stderr_tail) > tail_limit:
                        del stderr_tail[:-tail_limit]
            return_code = await process.wait()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa
            self.logger.exception(
                f"Failed to monitor task process {process.pid} ({task_name})"
            )
            return
        finally:
            if process.returncode is not None:
                self._processes.pop(process.pid, None)
            stopped_during_shutdown = process.pid in self._shutdown_processes
            self._shutdown_processes.discard(process.pid)

        if return_code == 0:
            self.logger.info(
                f"Task process {process.pid} ({task_name}) completed successfully"
            )
            return

        if stopped_during_shutdown:
            self.logger.info(
                f"Task process {process.pid} ({task_name}) stopped during task-manager shutdown"
            )
            return

        detail = stderr_tail.decode(errors="replace").strip() or "no stderr output"
        self.logger.error(
            f"Task process {process.pid} ({task_name}) exited with code {return_code}. "
            f"stderr tail:\n{detail}",
        )
        self._record_abnormal_exit(process.pid, return_code, detail)

    def _record_abnormal_exit(
        self,
        pid: int,
        return_code: int,
        stderr_tail: str,
    ) -> None:
        """Persist a terminal failure when a worker cannot report its own exit."""
        if return_code < 0:
            signal_number = -return_code
            try:
                signal_name = signal.Signals(signal_number).name
            except ValueError:
                signal_name = f"signal {signal_number}"
            exit_code = min(255, 128 + signal_number)
            error = f"Worker terminated by signal {signal_name} ({signal_number})"
        else:
            exit_code = min(255, return_code)
            error = f"Worker exited unexpectedly with code {return_code}"

        if stderr_tail != "no stderr output":
            error = f"{error}: {stderr_tail[-2048:]}"

        changed = False
        now = datetime.now(UTC)
        for status in self._statuses.values():
            if status.pid == pid and not status.state.is_terminal:
                status.state = TaskState.FAILED
                status.finished_at = now
                status.exit_code = exit_code
                status.error = error
                changed = True
        if changed:
            self._save_status()
        else:
            # The worker can exit before its first asynchronous status report
            # reaches the manager. Reconcile it when that snapshot arrives.
            self._abnormal_exits[pid] = (exit_code, error, now)

    @staticmethod
    def _task_name(argv: Sequence[str]) -> str:
        return task_name_from_argv(argv) or "unknown"

    async def set_status(self, task_id: str, status: TaskStatus) -> None:
        if task_id != status.task_id:
            raise ValueError("Task status ID does not match task_id")
        if task_id in self._deleted_task_ids:
            return
        current = self._statuses.get(task_id)
        if current is not None and current.state.is_terminal:
            # A worker snapshot may already be in flight when cancellation or
            # abnormal-exit reconciliation persists a terminal state.
            if current.state == TaskState.CANCELLED or not status.state.is_terminal:
                return
        snapshot = status.model_copy(deep=True)
        self._attach_log_path(snapshot)
        if snapshot.pid is not None and not snapshot.state.is_terminal:
            abnormal_exit = self._abnormal_exits.pop(snapshot.pid, None)
            if abnormal_exit is not None:
                snapshot.exit_code, snapshot.error, snapshot.finished_at = abnormal_exit
                snapshot.state = TaskState.FAILED
        self._statuses[task_id] = snapshot
        self._save_status()

    async def list_runtime_task_ids(self):
        return sorted(self._statuses)

    async def list_runtime_task_statuses(self):
        for status in self._statuses.values():
            self._attach_log_path(status)
        return [
            self._statuses[task_id].model_copy(deep=True)
            for task_id in sorted(self._statuses, reverse=True)
        ]

    async def get_status(self, task_id):
        self._attach_log_path(self._statuses[task_id])
        return self._statuses[task_id].model_copy(deep=True)

    async def cancel(self, task_id: str) -> bool:
        status = self._statuses[task_id]
        if (
            status.pid is None
            or status.state.is_terminal
            or not self._signal(status.pid, signal.SIGKILL)
        ):
            return False
        status.state = TaskState.CANCELLED
        status.finished_at = datetime.now(UTC)
        status.exit_code = 130
        self._save_status()
        return True

    async def delete(self, task_ids: Sequence[str]) -> list[str]:
        if isinstance(task_ids, (str, bytes)) or not all(
            isinstance(task_id, str) for task_id in task_ids
        ):
            raise TypeError("task_ids must be a sequence of strings")

        deleted = []
        for task_id in dict.fromkeys(task_ids):
            status = self._statuses.get(task_id)
            if status is not None and status.state.is_terminal:
                del self._statuses[task_id]
                self._deleted_task_ids.add(task_id)
                deleted.append(task_id)
        if deleted:
            self._save_status()
        return deleted

    @staticmethod
    def _signal(pid: int, sig: signal.Signals) -> bool:
        try:
            os.killpg(pid, sig)
        except ProcessLookupError:
            return False
        return True
