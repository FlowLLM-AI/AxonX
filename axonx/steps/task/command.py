"""Task mutation Steps."""

from ...components.job.events import ProgressEvent
from ...components.registry import provider
from ...enums import TaskState
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


@provider("wait_task")
class WaitTaskStep(TaskManagerStep):
    """Wait for a submitted run and return its terminal status."""

    async def execute(self):
        status = await self.task_manager.wait(
            self.context["task_id"],
            self.context["run_id"],
            self.context.get("poll_interval", 1.0),
        )
        self.response.answer = status
        self.response.success = status.state == TaskState.SUCCEEDED


@provider("cancel")
class CancelTaskStep(TaskManagerStep):
    async def execute(self):
        self.response.answer = await self.task_manager.cancel(self.context["task_id"])


@provider("delete")
class DeleteTasksStep(TaskManagerStep):
    async def execute(self):
        self.response.answer = await self.task_manager.delete(self.context["task_ids"])
