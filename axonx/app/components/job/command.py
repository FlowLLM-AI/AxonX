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

from ....client.config import (
    AXONX_CLI_REQUEST_ID,
    AXONX_SERVICE_TARGET,
)
from ....client.events import JobEvent
from ....task.models.events import LogEvent
from ....utils.async_work import complete_on_cancel
from .response import RESPONSE_CALLBACKS

if TYPE_CHECKING:
    from ...core.context import ApplicationContext

OUTPUT_LIMIT = 1024 * 1024


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
    callbacks = service.cli_callbacks if service is not None else {}
    processes = service.cli_processes if service is not None else set()
    callbacks[request_id] = RESPONSE_CALLBACKS.get()
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
    try:
        process = await complete_on_cancel(spawn)
    except BaseException:
        callbacks.pop(request_id, None)
        if not spawn.cancelled() and spawn.exception() is None:
            process = spawn.result()
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            await complete_on_cancel(process.wait())
        raise
    processes.add(process.pid)
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    truncated = set()

    async def read(channel, stream):
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        while chunk := await stream.read(8192):
            remaining = OUTPUT_LIMIT - len(buffers[channel])
            buffers[channel].extend(chunk[:remaining])
            if len(chunk) > remaining:
                truncated.add(channel)
            await emit(LogEvent(channel=channel, content=decoder.decode(chunk)))
        tail = decoder.decode(b"", final=True)
        if tail:
            await emit(LogEvent(channel=channel, content=tail))

    try:
        async with asyncio.TaskGroup() as group:
            group.create_task(read("stdout", process.stdout))
            group.create_task(read("stderr", process.stderr))
            await process.wait()
    finally:

        async def cleanup():
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await process.wait()
            processes.discard(process.pid)
            callbacks.pop(request_id, None)

        await complete_on_cancel(cleanup())
    return process.returncode == 0, {
        **{name: value.decode(errors="replace") for name, value in buffers.items()},
        "exit_code": process.returncode,
        "stdout_truncated": "stdout" in truncated,
        "stderr_truncated": "stderr" in truncated,
    }
