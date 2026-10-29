"""Replay and follow a Task's durable progress and log streams."""

from __future__ import annotations

import asyncio
import math
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Any

from ....task.models.events import TASK_EVENT_ADAPTER, LogEvent, TaskEvent
from ....task.models.lifecycle import TaskMetadata
from ....task.storage.logs import LOG_WINDOW_BYTES, TaskJournal, TaskLogReader
from ....task.storage.workspace import EVENTS_FILE, task_path

MetadataReader = Callable[[str], Awaitable[TaskMetadata]]


class TaskEventStream:
    """Merge durable progress and text logs; each follower owns independent cursors."""

    def __init__(
        self,
        workspace: Path,
        logs: TaskLogReader,
        read_metadata: MetadataReader,
        logger: Any,
    ) -> None:
        self.workspace = workspace
        self.logs = logs
        self.read_metadata = read_metadata
        self.logger = logger

    async def follow(self, task_id: str, poll_interval: float) -> AsyncIterator[TaskEvent]:
        """Replay and follow one execution, refusing to silently switch to a restart."""
        if not math.isfinite(poll_interval) or poll_interval <= 0:
            raise ValueError("poll_interval must be finite and positive")
        journal = TaskJournal(task_path(self.workspace, task_id) / EVENTS_FILE)
        log_path = None
        log_offset = events_offset = 0
        log_warned = False
        terminal_end = None
        started_at = None
        while True:
            status = await self.read_metadata(task_id)
            if started_at is not None and status.started_at != started_at:
                raise ValueError(f"Task restarted: {task_id}")
            started_at = status.started_at
            try:
                current_log_path = self.logs.path(status)
            except ValueError:
                current_log_path = None
            if current_log_path != log_path:
                log_path = current_log_path
                log_offset = 0
                log_warned = False
                terminal_end = None

            if status.state.is_terminal and terminal_end is None:
                terminal_end = await self._terminal_log_end(status, log_path, log_offset)

            events_offset, lines = await asyncio.to_thread(journal.read, events_offset)
            for line in lines:
                try:
                    event = TASK_EVENT_ADAPTER.validate_json(line)
                except ValueError as exc:
                    self.logger.warning(f"Ignoring malformed Task event: task_id={task_id} error={exc}")
                else:
                    yield event

            limit = LOG_WINDOW_BYTES
            if terminal_end is not None:
                # Reset the reader if the log rotated or was truncated before
                # its terminal snapshot.
                remaining = max(1, terminal_end) if log_offset > terminal_end else terminal_end - log_offset
                limit = min(limit, remaining)
            if limit <= 0:
                return
            try:
                chunk = await asyncio.to_thread(self.logs.read_status, status, log_offset, limit)
            except (OSError, ValueError) as exc:
                log_has_more = log_advanced = False
                if not log_warned:
                    self.logger.warning(f"Task log cannot be followed: task_id={task_id} error={exc}")
                    log_warned = True
            else:
                if chunk.content or chunk.reset:
                    yield LogEvent.from_chunk(chunk)
                log_advanced = chunk.next_offset != log_offset
                log_offset = chunk.next_offset
                log_has_more = chunk.has_more_after

            if terminal_end is not None:
                if log_offset < terminal_end and log_advanced:
                    continue
                return

            if log_has_more and log_advanced:
                continue
            await asyncio.sleep(poll_interval)

    async def _terminal_log_end(self, status: TaskMetadata, path: Path | None, offset: int) -> int:
        """Freeze the completed Task's boundary even when siblings keep writing its process log."""
        if status.replica and status.replica.log:
            return status.replica.log.end
        if self.logs.is_task_log(path):
            try:
                return (await asyncio.to_thread(path.stat)).st_size
            except OSError:
                pass
        return offset
