"""Read schedules from the selected execution service."""

from ..components.registry import provider
from .base import BaseStep


@provider("list_schedules_step")
class ListSchedulesStep(BaseStep):
    async def execute(self):
        self.response.answer = [scheduler.describe() for scheduler in self.app_context.schedulers.values()]
