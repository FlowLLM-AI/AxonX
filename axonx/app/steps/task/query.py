"""Read-only Task query Steps."""

import asyncio
from pathlib import Path

from ....common.logs import LogEvent
from ....common.registry import provider
from ....task.enums import TaskState
from ....task.query.summary import summarize_status, task_sort_key
from ....task.storage.logs import TaskLogReader
from .base import TaskRepositoryStep


@provider("list_ids")
class ListTaskIdsStep(TaskRepositoryStep):
    async def execute(self):
        self.response.answer = [item.task_id for item in await self.task_repository.summaries()]


@provider("list_statuses")
class ListTaskStatusesStep(TaskRepositoryStep):
    async def execute(self):
        detail = self.context.get("detail", "summary")
        if detail not in {"summary", "full"}:
            raise ValueError("detail must be summary or full")
        filters = {key: self.context[key] for key in ("task_type", "state") if self.context.get(key) is not None}
        if detail == "summary":
            self.response.answer = await self.task_repository.summaries(**filters)
        else:
            entries = await self.task_repository.entries(**filters)
            self.response.answer = sorted(entries.values(), key=task_sort_key, reverse=True)


@provider("get_status")
class GetTaskStatusStep(TaskRepositoryStep):
    async def execute(self):
        status = await self.task_repository.entry(self.context["task_id"])
        self.response.answer = summarize_status(status) if self.context.get("detail") == "summary" else status


@provider("read_log")
class ReadTaskLogStep(TaskRepositoryStep):
    async def execute(self):
        status = await self.task_repository.entry(self.context["task_id"])
        if (run_id := self.context.get("run_id")) is not None and status.run_id != run_id:
            raise ValueError(f"Task run changed: {status.task_id}")
        logs = TaskLogReader(Path(self.app_config.log_dir).expanduser().resolve())
        chunk = await asyncio.to_thread(
            logs.read_status,
            self.workspace_path,
            status,
            self.context.get("offset", -1),
            self.context.get("limit", 8192),
        )
        # The same shape serves the query and the stream, so a reader can seek
        # through history and follow the live tail with one handler.
        await self.emit(LogEvent.from_chunk(chunk))
        self.response.answer = chunk


@provider("get_task_graph_step")
class GetTaskGraphStep(TaskRepositoryStep):
    async def execute(self):
        self.response.answer = await self.task_repository.graph(self.context["task_id"])


@provider("wait_task")
class WaitTaskStep(TaskRepositoryStep):
    """Wait for one exact Run without controlling its execution."""

    async def execute(self):
        task_id, run_id = self.context["task_id"], self.context["run_id"]
        poll_interval = self.context.get("poll_interval", 1.0)
        if poll_interval <= 0:
            raise ValueError("poll_interval must be positive")
        while True:
            status = await self.task_repository.entry(task_id)
            if status.run_id != run_id:
                raise ValueError(f"Task run changed: {task_id}")
            if status.state.is_terminal:
                self.response.answer = summarize_status(status) if self.context.get("detail") == "summary" else status
                self.response.success = status.state == TaskState.SUCCEEDED
                return
            await asyncio.sleep(poll_interval)
