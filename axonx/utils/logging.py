"""Explicit process-wide Loguru configuration for AxonX."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Any

from loguru import logger

from ..constants import (
    AXONX_DEFAULT_ENCODING,
    AXONX_DEFAULT_LOG_DIR,
    LOG_ARGUMENT_MAX_LENGTH,
)

_LOG_FORMAT = "{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {extra[name]} | {file}:{line} | {function} | {message}"
_LOCK = RLock()
_LOG_PATH: Path | None = None


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

    def __post_init__(self) -> None:
        object.__setattr__(self, "log_dir", Path(self.log_dir))


def configure_logging(config: LoggingConfig) -> None:
    """Explicitly replace the process-wide AxonX logging sinks."""
    global _LOG_PATH
    with _LOCK:
        logger.remove()
        logger.configure(extra={"name": "axonx"})
        _LOG_PATH = None

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
            timestamp = datetime.now().astimezone().strftime("%Y-%m-%d_%H-%M-%S")
            _LOG_PATH = log_dir / f"{timestamp}_{os.getpid()}.log"
            logger.add(
                _LOG_PATH,
                level=config.level,
                format=_LOG_FORMAT,
                rotation="00:00",
                retention="7 days",
                compression="zip",
                encoding=AXONX_DEFAULT_ENCODING,
            )


def get_logger(name: str = "axonx") -> Any:
    """Return a named view without changing the logging configuration."""
    qualified_name = (
        name if name == "axonx" or name.startswith("axonx.") else f"axonx.{name}"
    )
    return logger.bind(name=qualified_name)


def get_log_path() -> Path | None:
    """Return the file receiving logs for the current process."""
    with _LOCK:
        return _LOG_PATH
