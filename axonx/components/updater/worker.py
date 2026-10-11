"""Standalone, standard-library-only updater copied outside the source tree before shutdown."""

from __future__ import annotations

import json
import os
import subprocess
import signal
import sys
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import TextIO

RECORD_ENV = "AXONX_UPDATE_RECORD"


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


def finish_startup(error: str | None = None) -> None:
    """Settle the update only after the replacement server is ready."""
    value = os.environ.pop(RECORD_ENV, None)
    if not value:
        return
    path = Path(value)
    record = json.loads(path.read_text(encoding="utf-8"))
    if record["phase"] == "starting":
        record.update(phase="failed" if error else "succeeded", error=error, after=versions())
        save(path, record)


def check_protected_paths(tracked: str, protected: list[str]) -> None:
    """Reject tracked files at, below or above runtime/configuration paths."""
    for file in filter(None, tracked.split("\0")):
        for path in protected:
            if file == path or file.startswith(path + "/") or path.startswith(file + "/"):
                raise ValueError(f"Protected runtime path overlaps tracked source: {path}")


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
    """Update the stopped service, then replace this process with its original command."""
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
                run("fetching", ["git", "fetch", "origin", "+refs/heads/main:refs/remotes/origin/main"], cwd)
                commit = run("fetching", ["git", "rev-parse", "origin/main"], cwd).strip()
                record["commit"] = commit
                tracked = run("fetching", ["git", "ls-tree", "-r", "--name-only", "-z", commit], cwd)
                check_protected_paths(tracked, plan["protected"])
                startup = Path(plan["cwd"]).relative_to(cwd)
                if startup != Path("."):
                    run("fetching", ["git", "cat-file", "-e", f"{commit}:{startup.as_posix()}"], cwd)
                run("cleaning", ["git", "reset", "--hard", "HEAD"], cwd)
                run("cleaning", ["git", "clean", "-fd", *plan["excludes"]], cwd)
                run("cleaning", ["git", "checkout", "-B", "main", commit], cwd)
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
            if not isinstance(exc, Exception):
                raise
        os.environ[RECORD_ENV] = str(path)
        try:
            os.chdir(plan["cwd"])
            os.execv(sys.executable, [sys.executable, "-m", "axonx.cli", *plan["arguments"]])
        except OSError as exc:
            record.update(phase="failed", error=f"Restart failed: {exc}")
            save(path, record)
            raise


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, interrupted)
    execute(Path(sys.argv[1]))
