"""Run the local CLI in the service's Python environment."""

import asyncio
import codecs
import os
import signal
import sys
from pathlib import Path
from contextlib import suppress
from uuid import uuid4

from ...components.job.events import LogEvent
from ...components.registry import provider
from ...constants import (
    AXONX_CLI_REQUEST_ID,
    AXONX_SERVICE_TARGET,
    AXONX_TASK_LOG_DIR,
    AXONX_TASK_TIMEZONE,
    AXONX_TASK_WORKSPACE_DIR,
)
from ...utils.async_work import complete_on_cancel
from ...utils.target import normalize_target
from ..base import BaseStep

OUTPUT_LIMIT = 1024 * 1024


@provider("cli_step")
class CliStep(BaseStep):
    """Forward stdout/stderr and preserve the child process's exit code."""

    async def execute(self):
        from ...cli.parser import parse_command
        from ...components.updater.manager import RESPONSE_CALLBACKS

        argv = self.context["argv"]
        command, options = parse_command(argv)
        if command.action in {"start", "cli"} or options.target is not None:
            raise ValueError("Remote CLI cannot start a service or forward to another target")
        if self.app_context.metadata.get("stopping"):
            raise RuntimeError("Service is stopping")
        service = self.app_context.service
        workspace = self.workspace_path.resolve()
        host = "127.0.0.1" if service.host == "0.0.0.0" else service.host
        host = f"[{host}]" if ":" in host else host
        request_id = uuid4().hex
        environment = {
            **os.environ,
            **self.app_config.environment,
            AXONX_SERVICE_TARGET: normalize_target(f"{host}:{service.port}"),
            "AXONX_SERVICE_TOKEN": service.token or "",
            AXONX_TASK_WORKSPACE_DIR: str(workspace),
            AXONX_TASK_LOG_DIR: str(Path(self.app_config.log_dir).expanduser().resolve()),
            AXONX_TASK_TIMEZONE: self.app_config.timezone,
            AXONX_CLI_REQUEST_ID: request_id,
        }
        environment["PYTHONPATH"] = os.pathsep.join(
            filter(None, (str(Path(__file__).resolve().parents[3]), environment.get("PYTHONPATH")))
        )
        service.cli_callbacks[request_id] = RESPONSE_CALLBACKS.get()
        spawn = asyncio.create_task(
            asyncio.create_subprocess_exec(
                sys.executable,
                "-u",
                "-m",
                "axonx.cli",
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
            service.cli_callbacks.pop(request_id, None)
            if not spawn.cancelled() and spawn.exception() is None:
                process = spawn.result()
                with suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
                await complete_on_cancel(process.wait())
            raise
        service.cli_processes.add(process.pid)
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
                service.cli_processes.discard(process.pid)
                service.cli_callbacks.pop(request_id, None)

            await complete_on_cancel(cleanup())
        self.response.success = process.returncode == 0
        self.response.answer = {
            **{name: value.decode(errors="replace") for name, value in buffers.items()},
            "exit_code": process.returncode,
            "stdout_truncated": "stdout" in truncated,
            "stderr_truncated": "stderr" in truncated,
        }
