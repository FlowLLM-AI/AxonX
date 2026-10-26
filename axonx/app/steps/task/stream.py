"""Follow one running task as a live event stream."""

from .base import TaskIndexStep
from ...registry import provider


@provider("stream_task")
class StreamTaskStep(TaskIndexStep):
    """Forward a task's progress and log until it stops.

    The events go out through the step's own ``emit`` channel, so the job that
    runs this step streams them without knowing where they came from — and folds
    to the same answer when nobody is streaming.
    """

    async def execute(self):
        task_id = self.context["task_id"]
        async for event in self.task_index.stream(task_id, self.context.get("poll_interval", 0.5)):
            await self.emit(event)
        # The stream only ends once the task is terminal, so this is its outcome.
        status = await self.task_index.entry(task_id)
        self.response.answer = status
        self.response.success = status.exit_code == 0
