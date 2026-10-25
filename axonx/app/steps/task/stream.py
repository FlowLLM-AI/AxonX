"""Follow one running task as a live event stream."""

from pathlib import Path

from .base import TaskIndexStep
from ....common.registry import provider
from ....task.query.stream import stream_task
from ....task.storage.logs import TaskLogReader


@provider("stream_task")
class StreamTaskStep(TaskIndexStep):
    """Forward a task's progress and log until it stops.

    The events go out through the step's own ``emit`` channel, so the job that
    runs this step streams them without knowing where they came from — and folds
    to the same answer when nobody is streaming.
    """

    async def execute(self):
        task_id = self.context["task_id"]
        logs = TaskLogReader(Path(self.app_config.log_dir).expanduser().resolve())
        async for event in stream_task(
            self.workspace_path,
            logs,
            self.task_index.entry,
            self.logger,
            task_id,
            self.context.get("poll_interval", 0.5),
        ):
            await self.emit(event)
        # The stream only ends once the task is terminal, so this is its outcome.
        status = await self.task_index.entry(task_id)
        self.response.answer = status
        self.response.success = status.exit_code == 0
