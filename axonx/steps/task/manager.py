"""Job adapters for task manager operations."""

from ...components.registry import R
from ..base import BaseStep


@R.register("list_ids")
class ListTaskIdsStep(BaseStep):
    async def execute(self):
        self.response.answer = await self.task_manager.list_ids()


@R.register("list_statuses")
class ListTaskStatusesStep(BaseStep):
    async def execute(self):
        statuses = await self.task_manager.list_statuses()
        self.response.answer = [status.model_dump(mode="json") for status in statuses]


@R.register("get_status")
class GetTaskStatusStep(BaseStep):
    async def execute(self):
        task_id = self.context["task_id"]
        try:
            status = await self.task_manager.get_status(task_id)
        except KeyError:
            self.response.success = False
            self.response.answer = f"Task not found: {task_id}"
            return
        self.response.answer = status.model_dump(mode="json")


@R.register("read_log")
class ReadTaskLogStep(BaseStep):
    async def execute(self):
        chunk = await self.task_manager.read_log(
            self.context["task_id"],
            self.context.get("offset", -1),
            self.context.get("limit", 65_536),
        )
        self.response.answer = chunk.model_dump(mode="json")


@R.register("cancel")
class CancelTaskStep(BaseStep):
    async def execute(self):
        self.response.answer = await self.task_manager.cancel(self.context["task_id"])


@R.register("delete")
class DeleteTasksStep(BaseStep):
    async def execute(self):
        self.response.answer = await self.task_manager.delete(self.context["task_ids"])
