"""Append Task progress journals and read journals and logs by byte offset."""

from __future__ import annotations

import codecs
import fcntl
import json
import os
from collections.abc import Iterable
from pathlib import Path

from ..models.events import LogChunk, ProgressEvent
from ..models.lifecycle import TaskMetadata, TaskStepStatus
from .workspace import read_entry, resolve_relative_path, task_directory

LOG_WINDOW_BYTES = 65_536


class TaskJournal:
    """Own one append-only JSONL journal; partial trailing lines wait for the next read."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, *events: ProgressEvent | dict, durable: bool = False) -> None:
        """Serialize appends and discard a trailing line interrupted by process exit."""
        if not events:
            return
        content = "".join(
            (
                event.model_dump_json()
                if isinstance(event, ProgressEvent)
                else json.dumps(event, ensure_ascii=False, allow_nan=False)
            )
            + "\n"
            for event in events
        ).encode()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        path = resolve_relative_path(self.path.parent, self.path.name)
        with path.open("a+b") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            end = handle.seek(0, os.SEEK_END)
            if end:
                handle.seek(end - 1)
                if handle.read(1) != b"\n":
                    position = end
                    while position:
                        start = max(0, position - 8192)
                        handle.seek(start)
                        chunk = handle.read(position - start)
                        boundary = chunk.rfind(b"\n")
                        if boundary >= 0:
                            handle.truncate(start + boundary + 1)
                            break
                        position = start
                    else:
                        handle.truncate(0)
            handle.write(content)
            if durable:
                handle.flush()
                os.fsync(handle.fileno())

    def append_snapshots(self, steps: Iterable[TaskStepStatus]) -> None:
        """Flush all step snapshots before publishing their terminal metadata."""
        self.append(*(ProgressEvent.from_status(step) for step in steps))

    def read(self, offset: int) -> tuple[int, list[str]]:
        """Read complete lines after a byte offset, restarting after truncation."""
        if offset < 0:
            raise ValueError("Invalid task journal offset")
        try:
            with self.path.open("rb") as handle:
                if offset > os.fstat(handle.fileno()).st_size:
                    offset = 0
                handle.seek(offset)
                data = handle.read()
        except FileNotFoundError:
            return offset, []
        complete = data.rfind(b"\n")
        if complete < 0:
            return offset, []
        lines = data[:complete].decode("utf-8", errors="replace").splitlines()
        return offset + complete + 1, lines


class TaskLogReader:
    """Read Task-local logs and bounded display snapshots inside one workspace."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory.expanduser().resolve()

    def path(self, status: TaskMetadata | None) -> Path | None:
        if status is None or not status.log_path:
            return None
        directory = resolve_relative_path(self.directory, task_directory(status.task_id))
        return resolve_relative_path(directory, status.log_path)

    def read_status(
        self,
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
        directory = resolve_relative_path(self.directory, task_directory(status.task_id))
        path = resolve_relative_path(directory, log.path)
        record = status.replica.files.get(log.path)
        if record is None or record.size != log.end - log.start or path.stat().st_size != record.size:
            raise ValueError("Replica log snapshot differs from its manifest")
        reset = offset >= 0 and (offset < log.start or offset > log.end)
        local = -1 if offset < 0 or reset else offset - log.start
        chunk = self.read(path, local, limit)
        current = read_entry(self.directory, status.task_id)
        if current is None or current.started_at != status.started_at or current.replica != status.replica:
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
        path = path.expanduser().resolve()
        if not self.is_task_log(path):
            raise ValueError("Task log path is outside the configured log directory")
        if not path.is_file():
            raise FileNotFoundError(f"Task log is unavailable: {path.name}")
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
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
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
