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

from .base_task_manager import BaseTaskManager
from ..component_registry import R
from ...constants import AXONX_SERVICE_INFO, AXONX_TASK_WORKSPACE_DIR
from ...enumeration import TaskState
from ...schema import TaskStatus


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

    def _save_status(self):
        payload = {
            "version": self.version,
            "tasks": [status.model_dump(mode="json") for status in self._statuses.values()],
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
                    statuses = (TaskStatus.model_validate(status) for status in data.get("tasks", []))
                    self._statuses = {status.task_id: status for status in statuses}
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
        processes = tuple(process for process in self._processes.values() if process.returncode is None)
        if not processes:
            return

        self._shutdown_processes.update(process.pid for process in processes)
        terminated = {process.pid for process in processes if self._signal(process.pid, signal.SIGTERM)}
        monitors = tuple(self._process_monitors)
        if monitors and self.terminate_grace_seconds > 0:
            await asyncio.wait(monitors, timeout=self.terminate_grace_seconds)

        survivors = tuple(process for process in processes if process.returncode is None)
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
        if isinstance(argv, (str, bytes)) or not all(isinstance(value, str) for value in argv):
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
            self.logger.exception(f"Failed to monitor task process {process.pid} ({task_name})")
            return
        finally:
            if process.returncode is not None:
                self._processes.pop(process.pid, None)
            stopped_during_shutdown = process.pid in self._shutdown_processes
            self._shutdown_processes.discard(process.pid)

        if return_code == 0:
            self.logger.info(f"Task process {process.pid} ({task_name}) completed successfully")
            return

        if stopped_during_shutdown:
            self.logger.info(f"Task process {process.pid} ({task_name}) stopped during task-manager shutdown")
            return

        detail = stderr_tail.decode(errors="replace").strip() or "no stderr output"
        self.logger.error(
            f"Task process {process.pid} ({task_name}) exited with code {return_code}. " f"stderr tail:\n{detail}",
        )

    @staticmethod
    def _task_name(argv: Sequence[str]) -> str:
        try:
            index = argv.index("--task")
            return argv[index + 1]
        except (ValueError, IndexError):
            return "unknown"

    async def set_status(self, task_id: str, status: TaskStatus) -> None:
        if task_id != status.task_id:
            raise ValueError("Task status ID does not match task_id")
        self._statuses[task_id] = status.model_copy(deep=True)
        self._save_status()

    async def list_runtime_task_ids(self):
        return sorted(self._statuses)

    async def list_runtime_task_statuses(self):
        return [self._statuses[task_id].model_copy(deep=True) for task_id in sorted(self._statuses, reverse=True)]

    async def get_status(self, task_id):
        return self._statuses[task_id].model_copy(deep=True)

    async def cancel(self, task_id: str) -> bool:
        status = self._statuses[task_id]
        if status.pid is None or status.state.is_terminal or not self._signal(status.pid, signal.SIGKILL):
            return False
        status.state = TaskState.CANCELLED
        status.finished_at = datetime.now(UTC)
        status.exit_code = 130
        self._save_status()
        return True

    @staticmethod
    def _signal(pid: int, sig: signal.Signals) -> bool:
        try:
            os.killpg(pid, sig)
        except ProcessLookupError:
            return False
        return True
