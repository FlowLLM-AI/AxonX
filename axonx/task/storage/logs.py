"""Read Task logs safely by byte offset."""

from __future__ import annotations

import codecs
from pathlib import Path

from ...constants import AXONX_DEFAULT_ENCODING
from ...logs import LogChunk
from .events import LOG_WINDOW_BYTES
from ..schemas.lifecycle import TaskMetadata
from .workspace import read_entry, task_path


class TaskLogReader:
    """Read logs while confining recorded paths to the configured log directory."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory.expanduser().resolve()

    @staticmethod
    def path(status: TaskMetadata | None) -> Path | None:
        if status is None or not status.log_path:
            return None
        return Path(status.log_path).expanduser().resolve()

    def read_status(
        self,
        workspace: Path,
        status: TaskMetadata,
        offset: int = -1,
        limit: int = LOG_WINDOW_BYTES,
    ) -> LogChunk:
        if status.replica is None:
            return self.read(self.path(status), offset, limit)
        if offset < -1 or limit <= 0:
            raise ValueError("Invalid task log range")
        log = status.replica.log
        if log is None:
            return LogChunk()
        directory = task_path(workspace, status.task_id)
        path = directory / log.path
        if not path.resolve().is_relative_to(directory.resolve()) or any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError("Replica log path escapes its Task")
        record = status.replica.files.get(log.path)
        if record is None or record.size != log.end - log.start or path.stat().st_size != record.size:
            raise ValueError("Replica log snapshot differs from its manifest")
        reset = offset >= 0 and (offset < log.start or offset > log.end)
        local = -1 if offset < 0 or reset else offset - log.start
        chunk = TaskLogReader(directory).read(path, local, limit)
        current = read_entry(workspace, status.task_id)
        if current is None or current.run_id != status.run_id or current.replica != status.replica:
            raise ValueError("Replica changed while reading logs; retry the current snapshot")
        return chunk.model_copy(
            update={
                "start_offset": chunk.start_offset + log.start,
                "next_offset": chunk.next_offset + log.start,
                "file_size": log.end,
                "reset": reset,
            }
        )

    def is_task_log(self, path: Path | None) -> bool:
        return path is not None and path.suffix == ".log" and path.is_relative_to(self.directory)

    def read(self, path: Path | None, offset: int = -1, limit: int = LOG_WINDOW_BYTES) -> LogChunk:
        if offset < -1 or limit <= 0:
            raise ValueError("Invalid task log range")
        if path is None:
            return LogChunk()
        if not self.is_task_log(path):
            raise ValueError("Task log path is outside the configured log directory")
        if not path.is_file():
            raise FileNotFoundError(f"Task log is unavailable (retained for 7 days): {path.name}")
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
        return LogChunk(
            content=content,
            start_offset=start_offset,
            next_offset=next_offset,
            file_size=file_size,
            has_more_before=start_offset > 0,
            has_more_after=next_offset < file_size,
            reset=reset,
        )
