"""Follow one running task as a live event stream."""

from ...components.registry import provider
from .base import TaskManagerStep


@provider("stream_task")
class StreamTaskStep(TaskManagerStep):
    """Forward a task's progress and log until it stops.

    The events go out through the step's own ``emit`` channel, so the job that
    runs this step streams them without knowing where they came from — and folds
    to the same answer when nobody is streaming.
    """

    async def execute(self):
        task_id = self.context["task_id"]
        async for event in self.task_manager.stream(
            task_id, self.context.get("poll_interval", 0.5)
        ):
            await self.emit(event)
        # The stream only ends once the task is terminal, so this is its outcome.
        status = await self.task_manager.get_status(task_id)
        self.response.answer = status
        self.response.success = status.exit_code == 0
