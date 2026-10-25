"""Machine identity and exact process inspection, signalling and waits."""

import math
import os
import plistlib
import subprocess
import sys
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from time import monotonic, sleep
from uuid import NAMESPACE_OID, UUID, uuid5

import psutil


@cache
def machine_id() -> str:
    """Identify the execution machine across service and operating-system restarts."""
    if sys.platform == "darwin":
        result = subprocess.run(
            ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice", "-a"],
            check=True,
            capture_output=True,
            timeout=10,
        )
        identifier = plistlib.loads(result.stdout)[0]["IOPlatformUUID"]
    elif sys.platform.startswith("linux"):
        for path in (Path("/etc/machine-id"), Path("/var/lib/dbus/machine-id")):
            try:
                identifier = path.read_text(encoding="utf-8").strip()
                if identifier:
                    break
            except FileNotFoundError:
                continue
        else:
            raise RuntimeError("Cannot identify the execution machine: no OS machine ID")
    else:
        raise NotImplementedError("Task execution supports macOS and Linux")
    return uuid5(NAMESPACE_OID, f"axonx:{UUID(identifier).hex}").hex


def process_started_at(pid: int | None = None) -> datetime:
    """Capture the process instance, rather than relying on a reusable PID."""
    return datetime.fromtimestamp(psutil.Process(os.getpid() if pid is None else pid).create_time(), UTC)


def process_instance(pid: int, started_at: datetime) -> psutil.Process | None:
    """Return the exact live process; access failures remain distinguishable from exit."""
    try:
        process = psutil.Process(pid)
        if abs(process.create_time() - started_at.timestamp()) > 0.001:
            return None
        if not process.is_running() or process.status() in {psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD}:
            return None
        return process
    except psutil.NoSuchProcess:
        return None


def signal_process(process: psutil.Process, *, force: bool = False) -> None:
    """Signal an exact process instance, never a reused PID."""
    if process.pid == os.getpid():
        raise ValueError("Cannot terminate the current process")
    try:
        process.kill() if force else process.terminate()
    except psutil.NoSuchProcess:
        pass


def wait_processes(processes: list[psutil.Process], timeout: float) -> None:
    """Wait for exact process instances, treating zombies as exited."""
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("Process timeout must be finite and positive")
    deadline = monotonic() + timeout

    def alive(process):
        try:
            return process_instance(process.pid, datetime.fromtimestamp(process.create_time(), UTC)) is not None
        except psutil.NoSuchProcess:
            return False

    while any(alive(p) for p in processes):
        if monotonic() >= deadline:
            raise TimeoutError("Process did not exit; retry kill with --force true")
        sleep(min(0.05, max(0, deadline - monotonic())))
