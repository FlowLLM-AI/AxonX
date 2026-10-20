"""Read schedules from the selected execution service."""

from ..components.registry import provider
from .base import BaseStep


@provider("list_schedules_step")
class ListSchedulesStep(BaseStep):
    async def execute(self):
        name = self.context.get("name")
        self.response.answer = [
            scheduler.describe(
                include_history=self.context.get("include_history", False),
                history_limit=self.context.get("history_limit", 20),
            )
            for scheduler in self.app_context.schedulers.values()
            if name is None or scheduler.name == name
        ]


@provider("list_studio_pages_step")
class ListStudioPagesStep(BaseStep):
    async def execute(self):
        self.response.answer = [
            {"id": name, **page.model_dump(mode="json")} for name, page in self.app_config.studio.pages.items()
        ]
