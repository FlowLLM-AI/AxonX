"""Stream a configured command's output from a managed child process."""

import asyncio
import codecs
import os
import signal
from contextlib import suppress
from uuid import uuid4

from ...protocol import AXONX_SERVICE_TARGET
from ..base import BaseStep
from ...async_work import complete_on_cancel
from ...connection import AXONX_CLI_REQUEST_ID, normalize_target
from ....task.models.logs import LogEvent
from ...registry import provider

OUTPUT_LIMIT = 1024 * 1024


@provider("command_step")
class CommandStep(BaseStep):
    """Forward stdout/stderr and preserve the child process's exit code."""

    async def execute(self):
        from ...core.response import RESPONSE_CALLBACKS

        argv = self.context["argv"]
        command = self.app_config.command
        if not command:
            raise RuntimeError("No application command is configured")
        if self.app_context.metadata.get("stopping"):
            raise RuntimeError("Service is stopping")
        service = self.app_context.service
        workspace = self.workspace.root
        request_id = uuid4().hex
        environment = {
            **os.environ,
            **self.app_config.environment,
            AXONX_CLI_REQUEST_ID: request_id,
        }
        if service is not None:
            host = "127.0.0.1" if service.host == "0.0.0.0" else service.host
            host = f"[{host}]" if ":" in host else host
            environment.update(
                {
                    AXONX_SERVICE_TARGET: normalize_target(f"{host}:{service.port}"),
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
                await self.emit(LogEvent(channel=channel, content=decoder.decode(chunk)))
            tail = decoder.decode(b"", final=True)
            if tail:
                await self.emit(LogEvent(channel=channel, content=tail))

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
        self.response.success = process.returncode == 0
        self.response.answer = {
            **{name: value.decode(errors="replace") for name, value in buffers.items()},
            "exit_code": process.returncode,
            "stdout_truncated": "stdout" in truncated,
            "stderr_truncated": "stderr" in truncated,
        }
