"""Seven-day retention for process logs, Run logs, and rotated archives."""

from __future__ import annotations

import fcntl
import os
import re
import stat
from pathlib import Path
from time import time

import psutil

LOG_RETENTION_SECONDS = 7 * 24 * 60 * 60
LOG_CLEANUP_INTERVAL = 60 * 60
_LOG_NAME = re.compile(
    r"\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_(?P<pid>\d+)" + r"(?P<run>_[a-f0-9]{64})?(?P<archive>\..+)?\.log(?:\.zip)?"
)


def cleanup_log_files(directory: Path) -> None:
    """Remove expired AxonX files, skipping live process logs and locked Runs.

    Run sinks hold an advisory lock for their lifetime, including quiet periods.
    Process logs rotate, so their live owner PID protects the current log instead.
    """
    cutoff = time() - LOG_RETENTION_SECONDS
    try:
        paths = list(directory.glob("*.log*"))
    except OSError:
        return
    for path in paths:
        match = _LOG_NAME.fullmatch(path.name)
        if match is None:
            continue
        if (
            match["run"] is None
            and match["archive"] is None
            and path.suffix == ".log"
            and psutil.pid_exists(int(match["pid"]))
        ):
            continue
        try:
            # Refuse symlinks and avoid blocking on a non-regular file.
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(descriptor, "rb") as handle:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                info = os.fstat(handle.fileno())
                if stat.S_ISREG(info.st_mode) and info.st_mtime < cutoff:
                    path.unlink()
        except OSError:
            # Missing files, active locks, or filesystem failures must not
            # interrupt logging or Task execution.
            continue
