"""Expose TaskManager operations through Application jobs."""

from ..base_step import BaseStep
from ...components import R
from ...constants import CLI_RAW_ARGUMENTS
from ...schema import TaskStatus


@R.register("submit_task")
class SubmitTask(BaseStep):
    """Submit the original CLI arguments to the default task manager."""

    async def execute(self):
        await self.task_manager.submit(self.context[CLI_RAW_ARGUMENTS])
        self.response.answer = None


@R.register("set_task_status")
class SetTaskStatus(BaseStep):
    """Store a complete status reported by a Task process."""

    async def execute(self):
        await self.task_manager.set_status(self.context["task_id"], TaskStatus.model_validate(self.context["status"]))
        self.response.answer = None


@R.register("list_tasks")
class ListTasks(BaseStep):
    """List all known task identifiers."""

    async def execute(self):
        self.response.answer = await self.task_manager.list_task_ids()


@R.register("get_task_status")
class GetTaskStatus(BaseStep):
    """Return one task status."""

    async def execute(self):
        status = await self.task_manager.get_status(self.context["task_id"])
        self.response.answer = status.model_dump(mode="json")


@R.register("cancel_task")
class CancelTask(BaseStep):
    """Cancel one queued or running task."""

    async def execute(self):
        self.response.answer = await self.task_manager.cancel(self.context["task_id"])
