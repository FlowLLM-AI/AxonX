"""Fixtures for credentialed, live-service integration tests."""

from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import httpx
import pytest

from axonx.utils import parse_env_file

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def require_claude_gateway() -> None:
    """Skip without exposing the gateway values in fixture tracebacks."""
    values = {**parse_env_file(PROJECT_ROOT / ".env"), **os.environ}
    required = ("CLAUDE_CODE_API_KEY", "CLAUDE_CODE_BASE_URL", "CLAUDE_CODE_MODEL_NAME")
    missing = [name for name in required if not values.get(name)]
    if missing:
        pytest.skip(f"live Claude gateway is not configured: {', '.join(missing)}")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="session")
def live_agent_service(tmp_path_factory, require_claude_gateway):
    """Start the real AxonX HTTP service with Shell and version Agent tools."""
    root = tmp_path_factory.mktemp("agent-service")
    port = _free_port()
    token = "agent-integration-stream"
    config = {
        "extends": "default",
        "workspace_dir": str(root / "workspace"),
        "enable_logo": False,
        "log_to_console": True,
        "log_to_file": False,
        "components": {
            "agent": {
                "default": {
                    "job_tools": ["shell", "version"],
                    "max_turns": 12,
                },
            },
        },
        "jobs": {
            "version": {
                "description": "Return the installed AxonX version.",
                "steps": [{"backend": "version_step"}],
            },
        },
        "service": {
            "backend": "http",
            "host": "127.0.0.1",
            "port": port,
            "web_enabled": False,
            "token": token,
        },
    }
    config_path = root / "integration.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    log_path = root / "service.log"
    environment = {**os.environ, "PYTHONUNBUFFERED": "1"}

    with log_path.open("w+", encoding="utf-8") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "axonx.cli", "start", "--config", str(config_path)],
            cwd=PROJECT_ROOT,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        deadline = time.monotonic() + 30
        url = f"http://127.0.0.1:{port}"
        while time.monotonic() < deadline:
            if process.poll() is not None:
                log.seek(0)
                pytest.fail(f"AxonX service exited during startup:\n{log.read()}")
            try:
                if httpx.get(
                    f"{url}/health",
                    headers={"authorization": f"Bearer {token}"},
                    timeout=0.5,
                ).is_success:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        else:
            process.terminate()
            process.wait(timeout=10)
            log.seek(0)
            pytest.fail(f"AxonX service did not become healthy:\n{log.read()}")

        yield {"port": port, "token": token, "log_path": log_path}

        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
