"""Job adapters for Task definitions, status, logs, streams, directories and context."""

import asyncio
from abc import ABC
from datetime import datetime
from pathlib import Path

from ...task.models.events import LogEvent
from ...task.models.identity import TaskState
from ...utils.async_work import run_blocking
from ..components.registry import provider
from ..components.task_index.base import BaseTaskIndex
from ..components.task_index.query import summarize_status, task_sort_key
from ..workspace.models import WorkspaceEntry
from .base import BaseStep


class TaskIndexStep(BaseStep, ABC):
    """A Step that reads one configured Task index."""

    @property
    def index(self) -> BaseTaskIndex:
        return self.component(BaseTaskIndex)


@provider("list_ids")
class ListTaskIdsStep(TaskIndexStep):
    async def execute(self):
        self.response.answer = [item.task_id for item in await self.index.summaries()]


@provider("list_statuses")
class ListTaskStatusesStep(TaskIndexStep):
    async def execute(self):
        detail = self.context.get("detail", "summary")
        if detail not in {"summary", "full"}:
            raise ValueError("detail must be summary or full")
        filters = {key: self.context[key] for key in ("task_type", "state") if self.context.get(key) is not None}
        if detail == "summary":
            self.response.answer = await self.index.summaries(**filters)
        else:
            entries = await self.index.entries(**filters)
            self.response.answer = sorted(entries.values(), key=task_sort_key, reverse=True)


@provider("get_status")
class GetTaskStatusStep(TaskIndexStep):
    async def execute(self):
        status = await self.index.entry(self.context["task_id"])
        self.response.answer = summarize_status(status) if self.context.get("detail") == "summary" else status


@provider("read_log")
class ReadTaskLogStep(TaskIndexStep):
    async def execute(self):
        status = await self.index.entry(self.context["task_id"])
        started_at = self.context.get("started_at")
        if started_at is not None and status.started_at != datetime.fromisoformat(started_at):
            raise ValueError(f"Task restarted: {status.task_id}")
        chunk = await self.index.read_log(
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
        self.response.answer = await self.index.graph(self.context["task_id"])


@provider("wait_task")
class WaitTaskStep(TaskIndexStep):
    """Wait for the current Task, refusing to silently follow a restart."""

    async def execute(self):
        task_id = self.context["task_id"]
        poll_interval = self.context.get("poll_interval", 1.0)
        if poll_interval <= 0:
            raise ValueError("poll_interval must be positive")
        status = await self.index.entry(task_id)
        started_at = status.started_at
        while True:
            if status.started_at != started_at:
                raise ValueError(f"Task restarted: {task_id}")
            if status.state.is_terminal:
                self.response.answer = summarize_status(status) if self.context.get("detail") == "summary" else status
                self.response.success = status.state == TaskState.SUCCEEDED
                return
            await asyncio.sleep(poll_interval)
            status = await self.index.entry(task_id)


@provider("stream_task")
class StreamTaskStep(TaskIndexStep):
    """Forward a task's progress and log until it stops.

    The events go out through the step's own ``emit`` channel, so the job that
    runs this step streams them without knowing where they came from — and folds
    to the same answer when nobody is streaming.
    """

    async def execute(self):
        task_id = self.context["task_id"]
        async for event in self.index.stream(task_id, self.context.get("poll_interval", 0.5)):
            await self.emit(event)
        # The stream only ends once the task is terminal, so this is its outcome.
        status = await self.index.entry(task_id)
        self.response.answer = status
        self.response.success = status.exit_code == 0


def _is_task_directory(path: Path, entry: WorkspaceEntry) -> bool:
    return entry.kind == "directory" and (path / "metadata.json").is_file()


@provider("task_directories")
class ListTaskDirectoriesStep(BaseStep):
    """List task directories that contain a metadata document."""

    async def execute(self):
        self.response.answer = await asyncio.to_thread(
            self.workspace.list_entries,
            self.context["path"],
            include=_is_task_directory,
        )


@provider("get_task_context_step")
class GetTaskContextStep(TaskIndexStep):

    async def execute(self):
        task_id = self.context["task_id"]
        self.response.answer = await self.index.context(task_id)


@provider("list_task_defs")
class ListTaskDefsStep(BaseStep):
    """List registered Tasks, optionally including their parameter schemas."""

    async def execute(self):
        def query():
            return self.app_context.task_catalog.definitions(include_schemas=self.context.get("include_schemas", True))

        self.response.answer = await run_blocking(query)


@provider("get_task_def")
class GetTaskDefStep(BaseStep):
    """Describe one registered Task without loading unrelated Tasks."""

    async def execute(self):
        self.response.answer = await run_blocking(self.app_context.task_catalog.definition, self.context["task"])
