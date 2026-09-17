"""Execute a shell command on the machine running this AxonX application."""

import asyncio
import os
import signal

from ...components.registry import R
from ..base import BaseStep


@R.register("shell_step")
class ShellStep(BaseStep):
    """Run one command and return its output and exit status."""

    async def execute(self):
        command = self.context["command"]
        timeout = self.context.get("timeout", 30)
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            self._kill_process_group(process)
            await process.communicate()
            self.response.success = False
            self.response.answer = {
                "stdout": "",
                "stderr": f"Command timed out after {timeout} seconds",
                "exit_code": None,
            }
            return
        except asyncio.CancelledError:
            self._kill_process_group(process)
            await process.communicate()
            raise

        self.response.success = process.returncode == 0
        self.response.answer = {
            "stdout": stdout.decode(errors="replace"),
            "stderr": stderr.decode(errors="replace"),
            "exit_code": process.returncode,
        }

    @staticmethod
    def _kill_process_group(process):
        if process.returncode is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
