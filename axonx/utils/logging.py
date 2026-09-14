"""Process-wide Loguru configuration for AxonX."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
import sys
from threading import RLock
from typing import Any

from loguru import logger

from ..constants import LOG_ARGUMENT_MAX_LENGTH

_LOG_FORMAT = "{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {extra[name]} | {file}:{line} | {function} | {message}"


def _write_stderr(message: object) -> None:
    """Write through the current stderr stream so test capture remains effective."""
    sys.stderr.write(str(message))


def format_log_arguments(arguments: Any) -> str:
    """Return a bounded representation suitable for invocation logs."""
    rendered = repr(arguments)
    return rendered if len(rendered) <= LOG_ARGUMENT_MAX_LENGTH else f"{rendered[: LOG_ARGUMENT_MAX_LENGTH - 3]}..."


@dataclass(frozen=True)
class LoggingConfig:
    """Settings applied to the shared Loguru instance."""

    log_dir: Path = Path("logs")
    level: str = "INFO"
    log_to_console: bool = True
    log_to_file: bool = True


class LoggerManager:
    """Configure shared Loguru sinks once and provide named loggers."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._initialized = False
        self._config: LoggingConfig | None = None
        self._log_path: Path | None = None

    @property
    def config(self) -> LoggingConfig | None:
        """Return the active configuration, if logging has been initialized."""
        return self._config

    @property
    def log_path(self) -> Path | None:
        """Return the active process log file, when file logging is enabled."""
        return self._log_path

    def configure(self, config: LoggingConfig, *, force: bool = False) -> None:
        """Initialize sinks, replacing them only when explicitly forced."""
        with self._lock:
            if self._initialized and not force:
                return

            logger.remove()
            logger.configure(extra={"name": "axonx"})
            self._log_path = None

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
                timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                self._log_path = log_dir / f"{timestamp}_{os.getpid()}.log"
                logger.add(
                    self._log_path,
                    level=config.level,
                    format=_LOG_FORMAT,
                    rotation="00:00",
                    retention="7 days",
                    compression="zip",
                    encoding="utf-8",
                )

            self._config = config
            self._initialized = True

    def get_logger(
        self,
        name: str = "axonx",
        *,
        log_dir: str | Path = "logs",
        level: str = "INFO",
        log_to_console: bool = True,
        log_to_file: bool = True,
        force_init: bool = False,
    ) -> Any:
        """Return a named view of the shared Loguru logger."""
        directory = Path(log_dir)
        self.configure(
            LoggingConfig(directory, level, log_to_console, log_to_file),
            force=force_init,
        )
        qualified_name = name if name == "axonx" or name.startswith("axonx.") else f"axonx.{name}"
        return logger.bind(name=qualified_name)


_LOGGER_MANAGER = LoggerManager()


def get_logger(
    name: str = "axonx",
    *,
    log_dir: str | Path = "logs",
    level: str = "INFO",
    log_to_console: bool = True,
    log_to_file: bool = True,
    force_init: bool = False,
) -> Any:
    """Return an AxonX logger configured through the shared manager."""
    return _LOGGER_MANAGER.get_logger(
        name,
        log_dir=log_dir,
        level=level,
        log_to_console=log_to_console,
        log_to_file=log_to_file,
        force_init=force_init,
    )


def get_log_path() -> Path | None:
    """Return the file receiving logs for the current process."""
    return _LOGGER_MANAGER.log_path
