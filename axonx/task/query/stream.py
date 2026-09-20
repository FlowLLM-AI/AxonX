"""Replay and follow a Task's durable progress and log streams."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Any

from ...components.job.events import JOB_EVENT_ADAPTER, JobEvent, LogEvent
from ..storage.events import LOG_WINDOW_BYTES, read_event_lines
from ..storage.logs import TaskLogReader
from ..storage.workspace import EVENTS_FILE, TaskStatus, task_path

StatusReader = Callable[[str], Awaitable[TaskStatus]]


async def stream_task(
    workspace: Path,
    logs: TaskLogReader,
    read_status: StatusReader,
    logger: Any,
    task_id: str,
    poll_interval: float,
) -> AsyncIterator[JobEvent]:
    """Merge one Task's journal and text log until it becomes terminal."""
    if poll_interval <= 0:
        raise ValueError("poll_interval must be positive")
    log_path = logs.path(await read_status(task_id))
    events_path = task_path(workspace, task_id) / EVENTS_FILE
    log_offset = events_offset = 0
    log_warned = False
    while True:
        events_offset, lines = await asyncio.to_thread(
            read_event_lines, events_path, events_offset
        )
        for line in lines:
            try:
                yield JOB_EVENT_ADAPTER.validate_json(line)
            except ValueError as exc:
                logger.warning(
                    f"Ignoring malformed Task event: task_id={task_id} error={exc}"
                )
        try:
            chunk = await asyncio.to_thread(
                logs.read, log_path, log_offset, LOG_WINDOW_BYTES
            )
        except (OSError, ValueError) as exc:
            log_has_more = False
            log_advanced = False
            if not log_warned:
                logger.warning(
                    f"Task log cannot be followed: task_id={task_id} error={exc}"
                )
                log_warned = True
        else:
            if chunk.content:
                yield LogEvent.from_chunk(chunk)
            log_advanced = chunk.next_offset != log_offset
            log_offset = chunk.next_offset
            log_has_more = chunk.has_more_after

        status = await read_status(task_id)
        if status.state.is_terminal:
            if not log_has_more or not log_advanced:
                return
            continue
        if log_has_more and log_advanced:
            continue
        await asyncio.sleep(poll_interval)
