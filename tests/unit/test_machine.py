"""Exercise machine capabilities independently of Steps and application assembly."""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest

from axonx.app.components.job.command import run_command
from axonx.app.components.machine import build_info
from axonx.app.components.machine.python import run_python
from axonx.app.core.application import Application


def test_build_identity_queries_the_checkout_containing_the_package(monkeypatch):
    commands = []

    def run(command, **_kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="revision\n")

    monkeypatch.setattr(build_info.subprocess, "run", run)
    assert build_info._git("rev-parse", "HEAD") == "revision"
    assert commands == [["git", "-C", str(Path(__file__).resolve().parents[2]), "rev-parse", "HEAD"]]


@pytest.mark.asyncio
async def test_python_execution_captures_both_streams_and_exit_status():
    success, output = await run_python("import sys; print('out'); print('error', file=sys.stderr); sys.exit(3)", 5)
    assert not success
    assert output.stdout == "out\n"
    assert output.stderr == "error\n"
    assert output.exit_code == 3


@pytest.mark.asyncio
async def test_python_execution_reports_timeout_and_reaps_the_process():
    success, output = await run_python("import time; time.sleep(60)", 0.05)
    assert not success
    assert output.exit_code is None
    assert "timed out" in output.stderr


@pytest.mark.asyncio
async def test_cancelling_a_command_reaps_its_process_and_clears_service_ownership(tmp_path):
    app = Application(
        workspace_dir=str(tmp_path),
        log_to_console=False,
        log_to_file=False,
        service={"backend": "http", "token": "test"},
        command=(sys.executable, "-u", "-c", "import os, time; print(os.getpid()); time.sleep(60)"),
    )
    started = asyncio.Event()
    process_ids = []

    async def emit(event):
        process_ids.append(int(event.content.strip()))
        started.set()

    async with app:
        task = asyncio.create_task(run_command(app.context, (), emit))
        try:
            await asyncio.wait_for(started.wait(), 5)
            assert process_ids[0] in app.context.service.cli_processes
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 5)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        assert not app.context.service.cli_processes
        assert not app.context.service.cli_callbacks
        with pytest.raises(ProcessLookupError):
            os.kill(process_ids[0], 0)
