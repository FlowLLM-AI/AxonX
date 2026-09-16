"""Worker subprocess supervision for the local Task manager."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import UTC, datetime
import os
import signal
import sys
from typing import Any

from .reconciliation import WorkerExit

ExitHandler = Callable[[WorkerExit], Awaitable[None]]


class TaskProcessSupervisor:
    """Launch, monitor, cancel, and reap local Task worker processes."""

    def __init__(self, grace_seconds: float, logger: Any, on_exit: ExitHandler) -> None:
        if grace_seconds < 0:
            raise ValueError("terminate_grace_seconds must not be negative")
        self.grace_seconds = grace_seconds
        self.logger = logger
        self.on_exit = on_exit
        self.processes: dict[int, Any] = {}
        self.monitors: set[asyncio.Task[None]] = set()
        self._shutdown_pids: set[int] = set()

    async def spawn(self, argv: Sequence[str], environment: Mapping[str, str], task_name: str) -> None:
        """Launch one isolated worker and start monitoring it."""
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "axonx.cli",
            "exec",
            *argv,
            env=dict(environment),
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        self.processes[process.pid] = process
        monitor = asyncio.create_task(
            self._monitor(process, task_name),
            name=f"axonx-task-monitor-{process.pid}",
        )
        self.monitors.add(monitor)
        monitor.add_done_callback(self.monitors.discard)

    async def cancel(self, pid: int) -> bool:
        """Kill a live managed process and report whether a signal was sent."""
        process = self.processes.get(pid)
        return process is not None and process.returncode is None and self._signal(pid, signal.SIGKILL)

    async def shutdown(self) -> set[int]:
        """Terminate and reap all workers, escalating to SIGKILL after grace."""
        processes = tuple(process for process in self.processes.values() if process.returncode is None)
        if not processes:
            return set()

        self._shutdown_pids.update(process.pid for process in processes)
        terminated = {process.pid for process in processes if self._signal(process.pid, signal.SIGTERM)}
        monitors = tuple(self.monitors)
        if monitors and self.grace_seconds > 0:
            await asyncio.wait(monitors, timeout=self.grace_seconds)

        for process in tuple(process for process in processes if process.returncode is None):
            if self._signal(process.pid, signal.SIGKILL):
                terminated.add(process.pid)

        if monitors:
            _, pending = await asyncio.wait(monitors, timeout=max(1, self.grace_seconds))
            for monitor in pending:
                monitor.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
        return terminated

    async def _monitor(self, process: Any, task_name: str) -> None:
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
        except Exception:  # noqa
            self.logger.exception(f"Failed to monitor task process {process.pid} ({task_name})")
            return
        finally:
            if process.returncode is not None:
                self.processes.pop(process.pid, None)
            stopped_during_shutdown = process.pid in self._shutdown_pids
            self._shutdown_pids.discard(process.pid)

        if return_code == 0:
            self.logger.info(f"Task process {process.pid} ({task_name}) completed successfully")
            return
        if stopped_during_shutdown:
            self.logger.info(f"Task process {process.pid} ({task_name}) stopped during task-manager shutdown")
            return

        detail = stderr_tail.decode(errors="replace").strip() or "no stderr output"
        self.logger.error(
            f"Task process {process.pid} ({task_name}) exited with code {return_code}. stderr tail:\n{detail}",
        )
        await self.on_exit(WorkerExit(process.pid, return_code, detail, datetime.now(UTC)))

    @staticmethod
    def _signal(pid: int, sig: signal.Signals) -> bool:
        try:
            os.killpg(pid, sig)
        except ProcessLookupError:
            return False
        return True
