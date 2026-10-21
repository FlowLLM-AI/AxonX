"""Stable local machine identity and exact worker process checks."""

import os
import plistlib
import subprocess
import sys
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
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


def process_is_alive(pid: int | None, started_at: datetime | None) -> bool:
    """Treat unavailable identity or permissions conservatively as still alive."""
    if pid is None or pid <= 0 or started_at is None:
        return True
    try:
        process = psutil.Process(pid)
        return (
            process_started_at(pid) == started_at
            and process.is_running()
            and process.status() not in {psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD}
        )
    except psutil.NoSuchProcess:
        return False
    except psutil.AccessDenied:
        return True
