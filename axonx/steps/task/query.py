"""Read-only Task query Steps."""

from ...components.job.events import LogEvent
from ...components.registry import provider
from ...task.storage.events import LOG_WINDOW_BYTES
from .base import TaskManagerStep


@provider("list_ids")
class ListTaskIdsStep(TaskManagerStep):
    async def execute(self):
        self.response.answer = await self.task_manager.list_ids()


@provider("list_statuses")
class ListTaskStatusesStep(TaskManagerStep):
    async def execute(self):
        self.response.answer = await self.task_manager.list_statuses()


@provider("get_status")
class GetTaskStatusStep(TaskManagerStep):
    async def execute(self):
        self.response.answer = await self.task_manager.get_status(
            self.context["task_id"]
        )


@provider("read_log")
class ReadTaskLogStep(TaskManagerStep):
    async def execute(self):
        chunk = await self.task_manager.read_log(
            self.context["task_id"],
            self.context.get("offset", -1),
            self.context.get("limit", LOG_WINDOW_BYTES),
        )
        # The same shape serves the query and the stream, so a reader can seek
        # through history and follow the live tail with one handler.
        await self.emit(LogEvent.from_chunk(chunk))
        self.response.answer = chunk


@provider("get_task_graph_step")
class GetTaskGraphStep(TaskManagerStep):
    async def execute(self):
        self.response.answer = await self.task_manager.get_graph(
            self.context["task_id"]
        )
