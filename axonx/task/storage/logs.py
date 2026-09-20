"""Read Task logs safely by byte offset."""

from __future__ import annotations

import codecs
from pathlib import Path

from ...constants import AXONX_DEFAULT_ENCODING
from .events import LOG_WINDOW_BYTES, TaskLogChunk
from .workspace import TaskStatus


class TaskLogReader:
    """Read logs while confining recorded paths to the configured log directory."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory.expanduser().resolve()

    @staticmethod
    def path(status: TaskStatus | None) -> Path | None:
        if status is None or not status.log_path:
            return None
        return Path(status.log_path).expanduser().resolve()

    def is_task_log(self, path: Path | None) -> bool:
        return (
            path is not None
            and path.suffix == ".log"
            and path.is_relative_to(self.directory)
        )

    def read(
        self, path: Path | None, offset: int = -1, limit: int = LOG_WINDOW_BYTES
    ) -> TaskLogChunk:
        if offset < -1 or limit <= 0:
            raise ValueError("Invalid task log range")
        if path is None:
            return TaskLogChunk()
        if not self.is_task_log(path):
            raise ValueError("Task log path is outside the configured log directory")
        if not path.is_file():
            raise FileNotFoundError(f"Task log does not exist: {path.name}")
        file_size = path.stat().st_size
        reset = offset > file_size
        tail = offset < 0 or reset
        start_offset = max(0, file_size - limit) if tail else offset
        requested_start = start_offset
        with path.open("rb") as handle:
            if tail:
                while start_offset > 0:
                    handle.seek(start_offset)
                    byte = handle.read(1)
                    if not byte or byte[0] & 0b1100_0000 != 0b1000_0000:
                        break
                    start_offset -= 1
            handle.seek(start_offset)
            data = handle.read(limit + 3)
        prefix = 0
        while prefix < len(data) and data[prefix] & 0b1100_0000 == 0b1000_0000:
            prefix += 1
        start_offset += prefix
        data = data[prefix:]
        allowance = limit + requested_start - start_offset if tail else limit - prefix
        end = min(len(data), max(0, allowance))
        while end < len(data) and data[end] & 0b1100_0000 == 0b1000_0000:
            end += 1
        data = data[:end]
        decoder = codecs.getincrementaldecoder(AXONX_DEFAULT_ENCODING)(errors="replace")
        content = decoder.decode(data, final=False)
        pending, _ = decoder.getstate()
        consumed = len(data) - len(pending)
        next_offset = start_offset + consumed
        return TaskLogChunk(
            content=content,
            start_offset=start_offset,
            next_offset=next_offset,
            file_size=file_size,
            has_more_before=start_offset > 0,
            has_more_after=next_offset < file_size,
            reset=reset,
        )
