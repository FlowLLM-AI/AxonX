"""Bounded local shell execution."""

import pytest

from axonx.steps.machine.shell import run_shell


@pytest.mark.asyncio
async def test_shell_output_is_bounded(monkeypatch):
    monkeypatch.setattr("axonx.steps.machine.shell.MAX_SHELL_OUTPUT_BYTES", 8)

    success, output = await run_shell("printf 1234567890", 1)

    assert success is True
    assert output.stdout == "12345678"
    assert output.stdout_truncated is True


@pytest.mark.asyncio
async def test_shell_timeout_terminates_the_process_group():
    success, output = await run_shell("sleep 1", 0.01)

    assert success is False
    assert output.exit_code is None
    assert "timed out" in output.stderr
