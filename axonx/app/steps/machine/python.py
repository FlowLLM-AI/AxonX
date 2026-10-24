"""Execute Python source in the service's interpreter without a shell."""

import asyncio
import os
import signal
import sys

from .contracts import PythonOutput

MAX_OUTPUT_BYTES = 1024 * 1024


class _PythonProtocol(asyncio.SubprocessProtocol):
    """Capture bounded output and track process exit separately from pipe EOF."""

    def __init__(self) -> None:
        loop = asyncio.get_running_loop()
        self.exited: asyncio.Future[None] = loop.create_future()
        self.completed: asyncio.Future[None] = loop.create_future()
        self.buffers = {1: bytearray(), 2: bytearray()}
        self.truncated: set[int] = set()
        self.open_pipes = {0, 1, 2}

    def pipe_data_received(self, fd: int, data: bytes) -> None:
        buffer = self.buffers[fd]
        remaining = MAX_OUTPUT_BYTES - len(buffer)
        buffer.extend(data[:remaining])
        if len(data) > remaining:
            self.truncated.add(fd)

    def pipe_connection_lost(self, fd: int, exc: Exception | None) -> None:
        self.open_pipes.discard(fd)
        self._complete()

    def process_exited(self) -> None:
        self.exited.set_result(None)
        self._complete()

    def _complete(self) -> None:
        if self.exited.done() and not self.open_pipes and not self.completed.done():
            self.completed.set_result(None)


async def run_python(code: str, timeout: float) -> tuple[bool, PythonOutput]:
    """Send multiline source over stdin to a fresh Python process."""
    source = code.encode("utf-8")
    transport, protocol = await asyncio.get_running_loop().subprocess_exec(
        _PythonProtocol,
        sys.executable,
        "-u",
        "-",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    timed_out = False
    try:
        stdin = transport.get_pipe_transport(0)
        stdin.write(source)
        stdin.write_eof()
        await asyncio.wait_for(asyncio.shield(protocol.completed), timeout)
    except asyncio.TimeoutError:
        timed_out = True
    finally:
        if not protocol.completed.done():
            try:
                os.killpg(transport.get_pid(), signal.SIGKILL)
            except ProcessLookupError:
                pass
        # Closing pipes releases inherited handles even when a descendant has
        # started its own session. Wait for reaping, independently of pipe EOF.
        transport.close()
        await asyncio.shield(protocol.exited)

    stdout, stderr = (protocol.buffers[fd].decode(errors="replace") for fd in (1, 2))
    if timed_out:
        message = f"Python execution timed out after {timeout:g} seconds"
        stderr = f"{stderr}\n{message}" if stderr else message
    exit_code = None if timed_out else transport.get_returncode()
    return not timed_out and exit_code == 0, PythonOutput(
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        stdout_truncated=1 in protocol.truncated,
        stderr_truncated=2 in protocol.truncated,
    )
