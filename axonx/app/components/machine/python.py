"""Execute Python source in the service's interpreter without a shell."""

import asyncio
import math
import os
import signal
import sys
from contextlib import suppress

from ....utils.async_work import complete_on_cancel
from .models import PythonOutput

MAX_OUTPUT_BYTES = 1024 * 1024


class _PythonProtocol(asyncio.SubprocessProtocol):
    """Capture bounded output and track process exit separately from pipe EOF."""

    def __init__(self) -> None:
        loop = asyncio.get_running_loop()
        self.exited: asyncio.Future[None] = loop.create_future()
        self.completed: asyncio.Future[None] = loop.create_future()
        self.buffers = {1: bytearray(), 2: bytearray()}
        self.truncated: set[int] = set()

    def pipe_data_received(self, fd: int, data: bytes) -> None:
        buffer = self.buffers[fd]
        remaining = MAX_OUTPUT_BYTES - len(buffer)
        buffer.extend(data[:remaining])
        if len(data) > remaining:
            self.truncated.add(fd)

    def process_exited(self) -> None:
        self.exited.set_result(None)

    def connection_lost(self, exc: Exception | None) -> None:
        self.completed.set_result(None)


async def run_python(code: str, timeout: float) -> PythonOutput:
    """Send multiline source over stdin to a fresh Python process."""
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        raise TypeError("Python timeout must be a number")
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("Python timeout must be finite and positive")
    source = code.encode("utf-8")
    spawn = asyncio.create_task(
        asyncio.get_running_loop().subprocess_exec(
            _PythonProtocol,
            sys.executable,
            "-u",
            "-",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        ),
    )
    timed_out = False
    try:
        transport, protocol = await complete_on_cancel(spawn)
        stdin = transport.get_pipe_transport(0)
        stdin.write(source)
        stdin.write_eof()
        try:
            await asyncio.wait_for(asyncio.shield(protocol.completed), timeout)
        except TimeoutError:
            timed_out = True
    finally:
        if not spawn.cancelled() and spawn.exception() is None:
            transport, protocol = spawn.result()
            # A successful parent can leave background descendants behind too.
            with suppress(ProcessLookupError):
                os.killpg(transport.get_pid(), signal.SIGKILL)
            # Reap the leader without waiting on pipes inherited by descendants
            # that started their own session.
            transport.close()
            await complete_on_cancel(protocol.exited)

    stdout, stderr = (protocol.buffers[fd].decode(errors="replace") for fd in (1, 2))
    if timed_out:
        message = f"Python execution timed out after {timeout:g} seconds"
        stderr = f"{stderr}\n{message}" if stderr else message
    exit_code = None if timed_out else transport.get_returncode()
    return PythonOutput(
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        stdout_truncated=1 in protocol.truncated,
        stderr_truncated=2 in protocol.truncated,
    )
