"""Python execution avoids shell quoting and keeps bounded subprocess contracts."""

import asyncio
import json
import os
import signal
import sys

import psutil
import pytest

from axonx.config import ApplicationConfig, ConfigResolver
from axonx.core import Application
from axonx.steps.machine.python import run_python


@pytest.mark.asyncio
async def test_python_multiline_source_uses_service_interpreter():
    value = "中文 'quotes' \"double\" \\backslash $HOME `pwd` $(pwd)"
    code = f"import json, sys\nvalue = {value!r}\nprint(json.dumps([sys.executable, value], ensure_ascii=False))\n"

    success, output = await run_python(code, 5)

    assert success is True
    assert json.loads(output.stdout) == [sys.executable, value]
    assert output.stderr == ""


@pytest.mark.asyncio
@pytest.mark.parametrize("code,expected", [("raise ValueError('bad')", "ValueError: bad"), ("if", "SyntaxError")])
async def test_python_errors_return_stderr_and_exit_status(code, expected):
    success, output = await run_python(code, 5)
    assert success is False
    assert output.exit_code == 1
    assert expected in output.stderr


@pytest.mark.asyncio
async def test_python_output_is_bounded_and_both_streams_drained(monkeypatch):
    monkeypatch.setattr("axonx.steps.machine.python.MAX_OUTPUT_BYTES", 8)
    success, output = await run_python("import sys\nprint('x' * 100000)\nprint('y' * 100000, file=sys.stderr)", 5)
    assert success is True
    assert output.stdout == "x" * 8
    assert output.stderr == "y" * 8
    assert output.stdout_truncated is True
    assert output.stderr_truncated is True


@pytest.mark.asyncio
async def test_python_large_source_is_sent_over_stdin():
    success, output = await run_python("#" + "x" * 300000 + "\nprint('ok')", 5)
    assert success is True
    assert output.stdout == "ok\n"


@pytest.mark.asyncio
async def test_python_timeout_preserves_partial_output():
    success, output = await run_python("import time\nprint('started')\ntime.sleep(10)", 1)
    assert success is False
    assert output.exit_code is None
    assert output.stdout == "started\n"
    assert "timed out" in output.stderr


@pytest.mark.asyncio
@pytest.mark.parametrize("detached", [False, True])
async def test_python_timeout_after_parent_exits_with_descendant_pipes_open(tmp_path, detached):
    marker = tmp_path / "child"
    code = (
        "import pathlib, subprocess, sys\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(10)'], "
        f"start_new_session={detached!r})\n"
        f"pathlib.Path({str(marker)!r}).write_text(str(child.pid))\n"
        "print('parent exited')"
    )
    try:
        success, output = await asyncio.wait_for(run_python(code, 1), 3)
        assert success is False
        assert output.exit_code is None
        assert output.stdout == "parent exited\n"
        assert "timed out" in output.stderr
    finally:
        if marker.exists():
            try:
                os.kill(int(marker.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass


@pytest.mark.asyncio
async def test_python_calls_have_independent_namespaces():
    success, _ = await run_python("private_value = 42", 5)
    assert success is True
    success, output = await run_python("print('private_value' in globals())", 5)
    assert success is True
    assert output.stdout == "False\n"


@pytest.mark.asyncio
@pytest.mark.parametrize("detached", [False, True])
@pytest.mark.parametrize("cancel", [False, True])
async def test_python_cleanup_does_not_wait_for_descendant_pipe_eof(tmp_path, detached, cancel):
    marker = tmp_path / "pids"
    code = (
        "import json, os, pathlib, subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(10)'], "
        f"start_new_session={detached!r})\n"
        f"pathlib.Path({str(marker)!r}).write_text(json.dumps([os.getpid(), child.pid]))\n"
        "print('started')\ntime.sleep(10)"
    )
    task = asyncio.create_task(run_python(code, 5 if cancel else 1))
    child_pid = None
    try:
        async with asyncio.timeout(5):
            while not marker.exists():
                await asyncio.sleep(0.01)
        pid, child_pid = json.loads(marker.read_text())
        if cancel:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 2)
        else:
            success, output = await asyncio.wait_for(task, 2)
            assert success is False
            assert output.exit_code is None
            assert output.stdout == "started\n"
            assert "timed out" in output.stderr
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
        if not detached and psutil.pid_exists(child_pid):
            assert psutil.Process(child_pid).status() == psutil.STATUS_ZOMBIE
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        if child_pid is not None:
            try:
                os.kill(child_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


@pytest.mark.asyncio
async def test_python_default_job_registration_and_validation(tmp_path):
    config = ApplicationConfig.model_validate(ConfigResolver().load("default"))
    app = Application(
        workspace_dir=str(tmp_path),
        log_to_console=False,
        log_to_file=False,
        jobs={"python": config.jobs["python"]},
    )
    job = app.context.jobs["python"]
    for invalid in ({}, {"code": ""}, {"code": "pass", "timeout": 0}, {"code": "pass", "timeout": 301}):
        with pytest.raises(ValueError):
            job.validate_arguments(invalid)
    async with app:
        response = await app.run_job("python", {"code": "print('job ok')"})
    assert response.success is True
    assert response.answer.stdout == "job ok\n"
