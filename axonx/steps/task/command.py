"""Task mutation Steps."""

from ...components.job.events import ProgressEvent
from ...components.registry import provider
from ...task.runtime.arguments import build_task_argv, split_task_arguments
from .base import TaskManagerStep


@provider("submit_task")
class SubmitTaskStep(TaskManagerStep):
    """Encode structured Task arguments and submit them to the manager."""

    async def execute(self):
        task_name, config = split_task_arguments(self.context)
        arguments = build_task_argv(task_name, config)
        handle = await self.task_manager.submit(arguments)
        await self.emit(ProgressEvent(name="submitted", percentage=100))
        self.response.answer = handle


@provider("cancel")
class CancelTaskStep(TaskManagerStep):
    async def execute(self):
        self.response.answer = await self.task_manager.cancel(self.context["task_id"])


@provider("delete")
class DeleteTasksStep(TaskManagerStep):
    async def execute(self):
        self.response.answer = await self.task_manager.delete(self.context["task_ids"])
