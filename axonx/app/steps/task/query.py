"""Read-only Task query Steps."""

import asyncio
from datetime import datetime

from .base import TaskIndexStep
from ....task.models.logs import LogEvent
from ...registry import provider
from ....task.task_enums import TaskState
from ....task.query import summarize_status, task_sort_key


@provider("list_ids")
class ListTaskIdsStep(TaskIndexStep):
    async def execute(self):
        self.response.answer = [item.task_id for item in await self.task_index.summaries()]


@provider("list_statuses")
class ListTaskStatusesStep(TaskIndexStep):
    async def execute(self):
        detail = self.context.get("detail", "summary")
        if detail not in {"summary", "full"}:
            raise ValueError("detail must be summary or full")
        filters = {key: self.context[key] for key in ("task_type", "state") if self.context.get(key) is not None}
        if detail == "summary":
            self.response.answer = await self.task_index.summaries(**filters)
        else:
            entries = await self.task_index.entries(**filters)
            self.response.answer = sorted(entries.values(), key=task_sort_key, reverse=True)


@provider("get_status")
class GetTaskStatusStep(TaskIndexStep):
    async def execute(self):
        status = await self.task_index.entry(self.context["task_id"])
        self.response.answer = summarize_status(status) if self.context.get("detail") == "summary" else status


@provider("read_log")
class ReadTaskLogStep(TaskIndexStep):
    async def execute(self):
        status = await self.task_index.entry(self.context["task_id"])
        started_at = self.context.get("started_at")
        if started_at is not None and status.started_at != datetime.fromisoformat(started_at):
            raise ValueError(f"Task restarted: {status.task_id}")
        chunk = await self.task_index.read_log(
            status,
            self.context.get("offset", -1),
            self.context.get("limit", 8192),
        )
        # The same shape serves the query and the stream, so a reader can seek
        # through history and follow the live tail with one handler.
        await self.emit(LogEvent.from_chunk(chunk))
        self.response.answer = chunk


@provider("get_task_graph_step")
class GetTaskGraphStep(TaskIndexStep):
    async def execute(self):
        self.response.answer = await self.task_index.graph(self.context["task_id"])


@provider("wait_task")
class WaitTaskStep(TaskIndexStep):
    """Wait for the current Task, refusing to silently follow a restart."""

    async def execute(self):
        task_id = self.context["task_id"]
        poll_interval = self.context.get("poll_interval", 1.0)
        if poll_interval <= 0:
            raise ValueError("poll_interval must be positive")
        status = await self.task_index.entry(task_id)
        started_at = status.started_at
        while True:
            if status.started_at != started_at:
                raise ValueError(f"Task restarted: {task_id}")
            if status.state.is_terminal:
                self.response.answer = summarize_status(status) if self.context.get("detail") == "summary" else status
                self.response.success = status.state == TaskState.SUCCEEDED
                return
            await asyncio.sleep(poll_interval)
            status = await self.task_index.entry(task_id)
