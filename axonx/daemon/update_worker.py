"""Standalone in-place updater. The daemon owns worker replacement."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import TextIO


def versions() -> dict[str, str | None]:
    """Read installed versions without importing application code."""
    result = {}
    for name in ("axonx", "axonx-studio"):
        try:
            result[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            result[name] = None
    return result


def save(path: Path, record: dict) -> None:
    """Atomically replace the durable record."""
    record["updated_at"] = datetime.now(UTC).isoformat()
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def kill_command_group(pid: int) -> None:
    """Release descendants even when their immediate parent has already exited."""
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def run_command(argv: list[str], cwd: str, log: TextIO, timeout: float = 1800) -> str:
    """Own each command's process group, including build/install descendants."""
    with subprocess.Popen(
        argv,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=log,
        text=True,
        start_new_session=True,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "PIP_NO_INPUT": "1"},
    ) as process:
        try:
            output, _ = process.communicate(timeout=timeout)
        finally:
            # Signal the owned group once, then drain its pipes and reap the command.
            kill_command_group(process.pid)
            process.communicate()
        log.write(output)
        log.flush()
        if process.returncode:
            raise subprocess.CalledProcessError(process.returncode, argv)
        return output


def interrupted(signum: int, _frame) -> None:
    """Turn service-manager termination into owned-command cleanup."""
    raise SystemExit(128 + signum)


def execute(path: Path) -> None:
    """Update source/packages, recording success or failure without replacing this process."""
    record = json.loads(path.read_text(encoding="utf-8"))
    plan = json.loads(path.with_name("plan.json").read_text(encoding="utf-8"))
    log_path = path.with_name("update.log")
    with log_path.open("a", encoding="utf-8") as log:

        def run(phase: str, argv: list[str], cwd: str) -> str:
            record["phase"] = phase
            save(path, record)
            log.write(f"{phase}: {argv!r}\n")
            log.flush()
            try:
                return run_command(argv, cwd, log)
            except subprocess.CalledProcessError as exc:
                raise RuntimeError(f"{phase} failed (exit {exc.returncode}); see update.log") from exc

        try:
            cwd = plan["cwd"]
            packages = ["--upgrade", "axonx", "axonx-studio"]
            if record["mode"] == "git":
                cwd = plan["repository"]
                run("fetching", ["git", "pull", "--ff-only"], cwd)
                record["commit"] = run("fetching", ["git", "rev-parse", "HEAD"], cwd).strip()
                studio = str(Path(cwd) / "axonx_studio")
                run("building", ["npm", "ci"], studio)
                run("building", ["npm", "run", "build"], studio)
                packages = ["-e", cwd, "-e", studio]
            if record["mode"] != "restart":
                run("installing", [sys.executable, "-m", "pip", "install", *packages], cwd)
                run("verifying", [sys.executable, "-m", "pip", "check"], cwd)
                run("verifying", [sys.executable, "-c", plan["verification"]], plan["cwd"])
            record.update(phase="starting", after=versions())
            save(path, record)
        except BaseException as exc:
            record.update(phase="failed", error=str(exc) or type(exc).__name__, after=versions())
            save(path, record)
            raise


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, interrupted)
    execute(Path(sys.argv[1]))
