"""Shared live CLI runner for the two Agent presentation scenarios."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]

PROMPT = """Use the provided AxonX MCP tools and perform exactly these steps:
1. Call the version tool.
2. Call the shell tool with the command: printf AXONX_REACT_OK
3. Call the version tool a second time.
Do not skip or combine calls. After all three tool results arrive, answer with
AXONX_REACT_DONE and briefly report both versions and the shell output.
"""


def run_live_cli(service: dict, job: str) -> str:
    """Run the real CLI, teeing each block to the terminal as it arrives."""
    command = [
        sys.executable,
        "-m",
        "axonx.cli",
        "--host-ip",
        "127.0.0.1",
        "--host-port",
        str(service["port"]),
        "--timeout",
        "180",
        "--stream",
        "true",
        "--stream-format",
        "blocks",
        "--token",
        service["token"],
        job,
        "--prompt",
        PROMPT,
    ]
    process = subprocess.Popen(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
    )
    assert process.stdout is not None
    output = []
    try:
        for line in process.stdout:
            print(line, end="", flush=True)
            output.append(line)
        return_code = process.wait(timeout=240)
    except BaseException:
        process.kill()
        process.wait(timeout=10)
        raise

    rendered = "".join(output)
    if return_code != 0:
        service_log = Path(service["log_path"]).read_text(encoding="utf-8")
        pytest.fail(
            f"CLI failed with exit code {return_code}\n"
            f"output:\n{rendered}\nservice log:\n{service_log}",
        )
    assert "===== BLOCK: Result =====" in rendered
    assert '"success": true' in rendered
    assert "AXONX_REACT_DONE" in rendered
    return rendered
