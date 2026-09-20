"""Worker subprocess supervision for the local Task manager."""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ....constants import CLI_EXEC_COMMAND

STDERR_TAIL_BYTES = 8 * 1024
REAP_TIMEOUT_SECONDS = 1.0
#: Variables a worker cannot work without, borrowed from this process when the
#: application does not set them itself. A task that shells out needs ``PATH``, and
#: a library that caches under the user's home needs ``HOME``. Everything else comes
#: from the application's own environment, which is what keeps an operator's shell
#: from reaching into a task by accident.
INHERITED_ENV = ("PATH", "HOME")


def pid_alive(pid: int | None) -> bool:
    """Whether a process ID still names a live process.

    ``kill(pid, 0)`` asks the kernel without signalling anything. A process this one
    may not signal is still a process, so a permission error means alive.
    """
    if pid is None or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


@dataclass(frozen=True)
class WorkerExit:
    return_code: int
    stderr_tail: str
    task_id: str
    run_id: str


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
        self.run_pids: dict[str, int] = {}
        self.monitors: set[asyncio.Task[None]] = set()
        self._shutdown_pids: set[int] = set()

    def is_managed_run(self, run_id: str) -> bool:
        """Whether this supervisor still tracks the task run."""
        return run_id in self.run_pids

    async def cancel_run(self, run_id: str) -> bool:
        """Terminate a managed task run, escalating after the configured grace."""
        pid = self.run_pids.get(run_id)
        if pid is None:
            return False
        return await self._cancel(pid)

    async def spawn(
        self,
        argv: Sequence[str],
        environment: Mapping[str, str],
        task_id: str,
        task_name: str,
        run_id: str,
    ) -> None:
        """Launch one isolated worker and start monitoring it.

        ``environment`` is layered over the few variables a child process cannot work
        without, rather than over this process's whole environment: a task receives
        the application's configuration, and nothing of the operator's shell by
        accident.
        """
        inherited = {key: os.environ[key] for key in INHERITED_ENV if key in os.environ}
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "axonx.cli",
            CLI_EXEC_COMMAND,
            *argv,
            env={**inherited, **environment},
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        self.processes[process.pid] = process
        self.run_pids[run_id] = process.pid
        monitor = asyncio.create_task(
            self._monitor(process, task_id, task_name, run_id),
            name=f"axonx-task-monitor-{process.pid}",
        )
        self.monitors.add(monitor)
        monitor.add_done_callback(self.monitors.discard)

    async def _cancel(self, pid: int) -> bool:
        process = self.processes.get(pid)
        if (
            process is None
            or process.returncode is not None
            or not self._signal(pid, signal.SIGTERM)
        ):
            return False
        try:
            await asyncio.wait_for(
                asyncio.shield(process.wait()), timeout=self.grace_seconds
            )
        except TimeoutError:
            if process.returncode is None:
                self._signal(pid, signal.SIGKILL)
            await process.wait()
        return True

    async def shutdown(self) -> set[str]:
        """Terminate and reap all workers, escalating to SIGKILL after grace."""
        processes = tuple(
            process for process in self.processes.values() if process.returncode is None
        )
        if not processes:
            return set()

        pids = {process.pid for process in processes}
        run_pids = {run_id: pid for run_id, pid in self.run_pids.items() if pid in pids}
        self._shutdown_pids.update(process.pid for process in processes)
        terminated = {
            process.pid
            for process in processes
            if self._signal(process.pid, signal.SIGTERM)
        }
        monitors = tuple(self.monitors)
        if monitors and self.grace_seconds > 0:
            await asyncio.wait(monitors, timeout=self.grace_seconds)

        survivors = tuple(
            process for process in processes if process.returncode is None
        )
        terminated.update(
            process.pid
            for process in survivors
            if self._signal(process.pid, signal.SIGKILL)
        )

        if monitors:
            # A killed worker only has to drain its pipe, so this is a short drain, not a second grace period.
            _, pending = await asyncio.wait(monitors, timeout=REAP_TIMEOUT_SECONDS)
            for monitor in pending:
                monitor.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
        return {run_id for run_id, pid in run_pids.items() if pid in terminated}

    async def _monitor(
        self, process: Any, task_id: str, task_name: str, run_id: str
    ) -> None:
        stderr_tail = bytearray()
        stopped_during_shutdown = False
        try:
            if process.stderr is not None:
                while chunk := await process.stderr.read(8192):
                    sys.stderr.write(chunk.decode(errors="replace"))
                    sys.stderr.flush()
                    stderr_tail.extend(chunk)
                    if len(stderr_tail) > STDERR_TAIL_BYTES:
                        del stderr_tail[:-STDERR_TAIL_BYTES]
            return_code = await process.wait()
        except Exception:
            self.logger.exception(
                f"Failed to monitor task process {process.pid} ({task_name})"
            )
            return
        finally:
            stopped_during_shutdown = process.pid in self._shutdown_pids
            self._shutdown_pids.discard(process.pid)
            # A worker that may still be alive after a monitor failure stays tracked
            # so cancellation and shutdown can still signal it; the reaper marks its
            # task failed once it disappears.
            if process.returncode is not None or stopped_during_shutdown:
                self.processes.pop(process.pid, None)
                self.run_pids.pop(run_id, None)

        if stopped_during_shutdown:
            self.logger.info(
                f"Task process {process.pid} ({task_name}) stopped during task-manager shutdown"
            )
            return

        detail = stderr_tail.decode(errors="replace").strip()
        if return_code:
            self.logger.error(
                f"Task process {process.pid} ({task_name}) exited with code {return_code}: {detail}"
            )
        else:
            self.logger.info(
                f"Task process {process.pid} ({task_name}) completed successfully"
            )
        try:
            await self.on_exit(WorkerExit(return_code, detail, task_id, run_id))
        except asyncio.CancelledError:
            raise
        except Exception:
            self.logger.exception(
                f"Failed to settle task process {process.pid} ({task_name})"
            )

    @staticmethod
    def _signal(pid: int, sig: signal.Signals) -> bool:
        try:
            os.killpg(pid, sig)
        except (ProcessLookupError, PermissionError):
            return False
        return True
