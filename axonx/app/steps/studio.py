"""Application-defined Studio navigation."""

from .base import BaseStep
from ...common.registry import provider


@provider("list_studio_pages_step")
class ListStudioPagesStep(BaseStep):
    async def execute(self):
        self.response.answer = [
            {"id": name, **page.model_dump(mode="json")} for name, page in self.app_config.studio.pages.items()
        ]
