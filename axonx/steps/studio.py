"""Application-defined Studio navigation."""

from ..components.registry import provider
from .base import BaseStep


@provider("list_studio_pages_step")
class ListStudioPagesStep(BaseStep):
    async def execute(self):
        self.response.answer = [
            {"id": name, **page.model_dump(mode="json")} for name, page in self.app_config.studio.pages.items()
        ]
