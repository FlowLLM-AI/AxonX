"""Replay and follow a Task's durable progress and log streams."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Any

from ..schemas.progress import TASK_EVENT_ADAPTER, TaskEvent
from ...common.logs import LogEvent
from ..storage.events import LOG_WINDOW_BYTES, read_event_lines
from ..storage.logs import TaskLogReader
from ..storage.workspace import EVENTS_FILE, task_path
from ..schemas.lifecycle import TaskMetadata

StatusReader = Callable[[str], Awaitable[TaskMetadata]]


async def stream_task(
    workspace: Path,
    logs: TaskLogReader,
    read_task_metadata: StatusReader,
    logger: Any,
    task_id: str,
    poll_interval: float,
) -> AsyncIterator[TaskEvent]:
    """Merge one Task's journal and text log until it becomes terminal."""
    if poll_interval <= 0:
        raise ValueError("poll_interval must be positive")
    events_path = task_path(workspace, task_id) / EVENTS_FILE
    log_path = None
    log_offset = events_offset = 0
    log_warned = False
    terminal_end = None
    while True:
        status = await read_task_metadata(task_id)
        current_log_path = logs.path(status)
        if current_log_path != log_path:
            log_path = current_log_path
            log_offset = 0
            log_warned = False
            terminal_end = None

        if status.state.is_terminal and terminal_end is None:
            # Legacy composites share a growing process log. Drain only the
            # snapshot observed at completion, rather than waiting for siblings.
            try:
                terminal_end = (
                    status.replica.log.end
                    if status.replica and status.replica.log
                    else (
                        (await asyncio.to_thread(log_path.stat)).st_size if logs.is_task_log(log_path) else log_offset
                    )
                )
            except OSError:
                terminal_end = log_offset

        events_offset, lines = await asyncio.to_thread(read_event_lines, events_path, events_offset)
        for line in lines:
            try:
                yield TASK_EVENT_ADAPTER.validate_json(line)
            except ValueError as exc:
                logger.warning(f"Ignoring malformed Task event: task_id={task_id} error={exc}")
        try:
            limit = LOG_WINDOW_BYTES
            if terminal_end is not None:
                # Preserve the reader's reset behavior if a legacy process log
                # rotated or was truncated before its terminal snapshot.
                remaining = max(1, terminal_end) if log_offset > terminal_end else terminal_end - log_offset
                limit = min(limit, remaining)
            if limit <= 0:
                return
            chunk = await asyncio.to_thread(logs.read_status, workspace, status, log_offset, limit)
        except (OSError, ValueError) as exc:
            log_has_more = False
            log_advanced = False
            if not log_warned:
                logger.warning(f"Task log cannot be followed: task_id={task_id} error={exc}")
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
