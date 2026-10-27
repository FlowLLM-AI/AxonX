"""Execute a service-owned CLI command with streaming output and cancellation cleanup."""

from __future__ import annotations

import asyncio
import codecs
import os
import signal
from collections.abc import Awaitable, Callable, Sequence
from contextlib import suppress
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from ....client.config import AXONX_CLI_REQUEST_ID, AXONX_SERVICE_TARGET
from ....client.events import JobEvent, LogEvent
from ....utils.async_work import complete_on_cancel
from .base import RESPONSE_CALLBACKS

if TYPE_CHECKING:
    from ...core.context import ApplicationContext

OUTPUT_LIMIT = 1024 * 1024


async def _read_output(
    stream: asyncio.StreamReader,
    channel: str,
    emit: Callable[[JobEvent], Awaitable[None]],
) -> tuple[str, bool]:
    """Stream all output while retaining only a bounded prefix for the response."""
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    buffer = bytearray()
    truncated = False
    while chunk := await stream.read(8192):
        remaining = OUTPUT_LIMIT - len(buffer)
        buffer.extend(chunk[:remaining])
        truncated |= len(chunk) > remaining
        if content := decoder.decode(chunk):
            await emit(LogEvent(channel=channel, content=content))
    if tail := decoder.decode(b"", final=True):
        await emit(LogEvent(channel=channel, content=tail))
    return buffer.decode(errors="replace"), truncated


async def _reap_process(process: asyncio.subprocess.Process) -> None:
    """Terminate the owned process group, including descendants, and reap its leader."""
    with suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGKILL)
    await process.wait()


async def run_command(
    app_context: ApplicationContext,
    argv: Sequence[str],
    emit: Callable[[JobEvent], Awaitable[None]],
) -> tuple[bool, dict[str, Any]]:
    """Run one CLI invocation, forwarding logs and reaping every owned process."""

    command = app_context.app_config.command
    if not command:
        raise RuntimeError("No application command is configured")
    if app_context.metadata.get("stopping"):
        raise RuntimeError("Service is stopping")
    service = app_context.service
    workspace = app_context.workspace.root
    request_id = uuid4().hex
    environment = {
        **os.environ,
        **app_context.app_config.environment,
        AXONX_CLI_REQUEST_ID: request_id,
    }
    if service is not None:
        environment.update(
            {
                AXONX_SERVICE_TARGET: service.local_target,
                "AXONX_SERVICE_TOKEN": service.token or "",
            }
        )
        service.cli_callbacks[request_id] = RESPONSE_CALLBACKS.get()
    spawn = asyncio.create_task(
        asyncio.create_subprocess_exec(
            *command,
            *argv,
            cwd=workspace,
            env=environment,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
    )
    process = None
    try:
        process = await complete_on_cancel(spawn)
        if service is not None:
            service.cli_processes.add(process.pid)
        async with asyncio.TaskGroup() as group:
            stdout = group.create_task(_read_output(process.stdout, "stdout", emit))
            stderr = group.create_task(_read_output(process.stderr, "stderr", emit))
            await process.wait()
    finally:
        try:
            if not spawn.cancelled() and spawn.exception() is None:
                process = spawn.result()
                await complete_on_cancel(_reap_process(process))
        finally:
            if service is not None:
                service.cli_callbacks.pop(request_id, None)
                if process is not None:
                    service.cli_processes.discard(process.pid)
    stdout_text, stdout_truncated = stdout.result()
    stderr_text, stderr_truncated = stderr.result()
    return process.returncode == 0, {
        "stdout": stdout_text,
        "stderr": stderr_text,
        "exit_code": process.returncode,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
    }
