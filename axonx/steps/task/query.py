"""Read-only Task query Steps."""

from ...components.job.events import LogEvent
from ...components.registry import provider
from ...task.query.summary import summarize_status
from .base import TaskManagerStep


@provider("list_ids")
class ListTaskIdsStep(TaskManagerStep):
    async def execute(self):
        self.response.answer = await self.task_manager.list_ids()


@provider("list_statuses")
class ListTaskStatusesStep(TaskManagerStep):
    async def execute(self):
        detail = self.context.get("detail", "summary")
        if detail not in {"summary", "full"}:
            raise ValueError("detail must be summary or full")
        filters = {key: self.context[key] for key in ("task_type", "state") if self.context.get(key) is not None}
        query = self.task_manager.list_summaries if detail == "summary" else self.task_manager.list_statuses
        self.response.answer = await query(**filters)


@provider("get_status")
class GetTaskStatusStep(TaskManagerStep):
    async def execute(self):
        status = await self.task_manager.get_status(self.context["task_id"])
        self.response.answer = summarize_status(status) if self.context.get("detail") == "summary" else status


@provider("read_log")
class ReadTaskLogStep(TaskManagerStep):
    async def execute(self):
        chunk = await self.task_manager.read_log(
            self.context["task_id"],
            self.context.get("offset", -1),
            self.context.get("limit", 8192),
            run_id=self.context.get("run_id"),
        )
        # The same shape serves the query and the stream, so a reader can seek
        # through history and follow the live tail with one handler.
        await self.emit(LogEvent.from_chunk(chunk))
        self.response.answer = chunk


@provider("get_task_graph_step")
class GetTaskGraphStep(TaskManagerStep):
    async def execute(self):
        self.response.answer = await self.task_manager.get_graph(self.context["task_id"])
