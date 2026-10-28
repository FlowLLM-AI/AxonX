"""Explicit process logging, file retention and bounded argument formatting."""

from __future__ import annotations

import fcntl
import os
import re
import stat
import sys
from collections.abc import Callable
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from threading import RLock
from time import time
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import psutil
from loguru import logger

LOG_RETENTION_SECONDS = 7 * 24 * 60 * 60
LOG_CLEANUP_INTERVAL = 60 * 60
LOG_ARGUMENT_MAX_LENGTH = 1000
_LOG_NAME = re.compile(
    r"\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_(?P<pid>\d+)(?P<task>_[a-f0-9]{64})?(?P<archive>\..+)?\.log(?:\.zip)?"
)
_LOG_FORMAT = (
    "{time:%Y-%m-%d %H:%M:%S} {extra[utc_offset]} | {level:<8} | "
    "{extra[name]} | {file}:{line} | {function} | {message}"
)
_LOCK = RLock()
_LOG_PATH: Path | None = None
_LOG_LEVEL = "INFO"


def _write_stderr(message: object) -> None:
    """Write through the current stderr stream so test capture remains effective."""
    sys.stderr.write(str(message))


@dataclass(frozen=True, slots=True)
class LoggingConfig:
    """Settings applied to the shared Loguru instance."""

    log_dir: Path = Path("logs")
    level: str = "INFO"
    log_to_console: bool = True
    log_to_file: bool = True
    timezone: str = "Asia/Shanghai"

    def __post_init__(self) -> None:
        object.__setattr__(self, "log_dir", Path(self.log_dir))


def configure_logging(config: LoggingConfig) -> None:
    """Explicitly replace the process-wide AxonX logging sinks."""
    global _LOG_PATH, _LOG_LEVEL
    try:
        log_timezone = ZoneInfo(config.timezone)
    except ZoneInfoNotFoundError:
        raise ValueError(f"Unknown timezone: {config.timezone!r}") from None

    def apply_timezone(record: dict[str, Any]) -> None:
        record["time"] = record["time"].astimezone(log_timezone)
        # Loguru's Z token calls tzinfo.utcoffset(None), which ZoneInfo does not support.
        offset = record["time"].strftime("%z")
        record["extra"]["utc_offset"] = f"{offset[:3]}:{offset[3:]}"

    with _LOCK:
        logger.remove()
        logger.configure(extra={"name": "axonx"}, patcher=apply_timezone)
        _LOG_PATH = None
        _LOG_LEVEL = config.level

        if config.log_to_console:
            logger.add(
                _write_stderr,
                level=config.level,
                format=_LOG_FORMAT,
                colorize=True,
            )

        if config.log_to_file:
            log_dir = config.log_dir.expanduser().resolve()
            log_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now(log_timezone).strftime("%Y-%m-%d_%H-%M-%S")
            _LOG_PATH = log_dir / f"{timestamp}_{os.getpid()}.log"
            logger.add(
                _LOG_PATH,
                level=config.level,
                format=_LOG_FORMAT,
                rotation="00:00",
                compression="zip",
                encoding="utf-8",
            )


def get_logger(name: str = "axonx") -> Any:
    """Return a named view without changing the logging configuration."""
    qualified_name = name if name == "axonx" or name.startswith("axonx.") else f"axonx.{name}"
    return logger.bind(name=qualified_name)


def get_log_path() -> Path | None:
    """Return the file receiving logs for the current process."""
    with _LOCK:
        return _LOG_PATH


@contextmanager
def log_file(path: Path, *, predicate: Callable[[dict], bool]):
    """Own a filtered file sink using the current process logging settings."""
    with _LOCK:
        sink = logger.add(path, level=_LOG_LEVEL, format=_LOG_FORMAT, encoding="utf-8", filter=predicate)
    try:
        yield
    finally:
        with _LOCK, suppress(ValueError):
            logger.remove(sink)


def cleanup_log_files(directory: Path) -> None:
    """Remove expired logs, protecting live process logs and locked Task logs."""
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
            match["task"] is None
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
            # Cleanup failures must not interrupt logging or Task execution.
            continue


def format_log_arguments(arguments: Any) -> str:
    """Return a bounded representation suitable for invocation logs."""
    rendered = repr(arguments)
    if len(rendered) <= LOG_ARGUMENT_MAX_LENGTH:
        return rendered
    return f"{rendered[: LOG_ARGUMENT_MAX_LENGTH - 3]}..."
