"""Task-submission step."""

from ...components import R
from ...constants import CLI_RAW_ARGUMENTS
from ..common.base_step import BaseStep


@R.register("submit_task")
class SubmitTaskStep(BaseStep):
    """Submit the original CLI arguments to the task manager."""

    async def execute(self):
        await self.task_manager.submit(self.context[CLI_RAW_ARGUMENTS])
        self.response.answer = None
