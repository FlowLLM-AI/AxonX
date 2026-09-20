"""Bounded shell-command execution for the local machine."""

import asyncio
import os
import signal

from .contracts import ShellOutput

MAX_SHELL_OUTPUT_BYTES = 1024 * 1024
SHELL_READ_BYTES = 64 * 1024


async def run_shell(command: str, timeout: float) -> tuple[bool, ShellOutput]:
    """Run a command while draining and discarding output beyond the cap."""
    process = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    stdout_task = asyncio.create_task(_read_stream(process.stdout))
    stderr_task = asyncio.create_task(_read_stream(process.stderr))
    timed_out = False
    try:
        await asyncio.wait_for(process.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        timed_out = True
        _kill_process_group(process)
        await process.wait()
    except asyncio.CancelledError:
        _kill_process_group(process)
        await process.wait()
        await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
        raise

    (stdout, stdout_truncated), (stderr, stderr_truncated) = await asyncio.gather(
        stdout_task, stderr_task
    )
    if timed_out:
        timeout_message = f"Command timed out after {timeout:g} seconds"
        stderr = f"{stderr}\n{timeout_message}" if stderr else timeout_message
    return not timed_out and process.returncode == 0, ShellOutput(
        stdout=stdout,
        stderr=stderr,
        exit_code=None if timed_out else process.returncode,
        stdout_truncated=stdout_truncated,
        stderr_truncated=stderr_truncated,
    )


async def _read_stream(stream: asyncio.StreamReader) -> tuple[str, bool]:
    captured = bytearray()
    truncated = False
    while chunk := await stream.read(SHELL_READ_BYTES):
        remaining = MAX_SHELL_OUTPUT_BYTES - len(captured)
        if remaining > 0:
            captured.extend(chunk[:remaining])
        if len(chunk) > remaining:
            truncated = True
    return captured.decode(errors="replace"), truncated


def _kill_process_group(process) -> None:
    if process.returncode is None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            pass
