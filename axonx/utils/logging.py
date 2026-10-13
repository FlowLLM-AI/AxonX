"""Explicit process-wide Loguru configuration for AxonX."""

from __future__ import annotations

import fcntl
import os
import sys
from contextlib import ExitStack, contextmanager, suppress
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from threading import RLock
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from loguru import logger

from ..constants import (
    AXONX_DEFAULT_ENCODING,
    AXONX_DEFAULT_LOG_DIR,
    AXONX_DEFAULT_TIMEZONE,
    LOG_ARGUMENT_MAX_LENGTH,
)
from .log_retention import cleanup_log_files

_LOG_FORMAT = (
    "{time:%Y-%m-%d %H:%M:%S} {extra[utc_offset]} | {level:<8} | "
    "{extra[name]} | {file}:{line} | {function} | {message}"
)
_LOCK = RLock()
_LOG_PATH: Path | None = None
_LOG_LEVEL = "INFO"
_TASK_RUNS: ContextVar[tuple[str, ...]] = ContextVar("axonx_log_task_runs", default=())


def _write_stderr(message: object) -> None:
    """Write through the current stderr stream so test capture remains effective."""
    sys.stderr.write(str(message))


def format_log_arguments(arguments: Any) -> str:
    """Return a bounded representation suitable for invocation logs."""
    rendered = repr(arguments)
    if len(rendered) <= LOG_ARGUMENT_MAX_LENGTH:
        return rendered
    return f"{rendered[: LOG_ARGUMENT_MAX_LENGTH - 3]}..."


@dataclass(frozen=True, slots=True)
class LoggingConfig:
    """Settings applied to the shared Loguru instance."""

    log_dir: Path = Path(AXONX_DEFAULT_LOG_DIR)
    level: str = "INFO"
    log_to_console: bool = True
    log_to_file: bool = True
    timezone: str = AXONX_DEFAULT_TIMEZONE

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
                encoding=AXONX_DEFAULT_ENCODING,
            )
            cleanup_log_files(log_dir)


def get_logger(name: str = "axonx") -> Any:
    """Return a named view without changing the logging configuration."""
    qualified_name = name if name == "axonx" or name.startswith("axonx.") else f"axonx.{name}"
    return logger.bind(name=qualified_name)


def get_log_path() -> Path | None:
    """Return the file receiving logs for the current process."""
    with _LOCK:
        return _LOG_PATH


@contextmanager
def task_log_scope(run_id: str):
    """Capture one Run and its nested children without capturing sibling Runs."""
    runs = (*_TASK_RUNS.get(), run_id)
    token = _TASK_RUNS.set(runs)
    try:
        with ExitStack() as stack:
            process_path = get_log_path()
            path = None
            if process_path is not None:
                identity = sha256(run_id.encode("utf-8")).hexdigest()
                path = process_path.with_name(f"{process_path.stem}_{identity}.log")
                handle = stack.enter_context(path.open("ab"))
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                sink = logger.add(
                    path,
                    level=_LOG_LEVEL,
                    format=_LOG_FORMAT,
                    encoding=AXONX_DEFAULT_ENCODING,
                    filter=lambda record: run_id in record["extra"].get("task_runs", ()),
                )
                stack.callback(_remove_sink, sink)
            with logger.contextualize(task_runs=runs):
                yield path
    finally:
        _TASK_RUNS.reset(token)


def _remove_sink(sink: int) -> None:
    # Reconfiguration may already have removed this process-wide sink.
    with suppress(ValueError):
        logger.remove(sink)
