"""Job adapter for a configured one-way task sender."""

from ..components.registry import provider
from ..components.sync.base import BaseSyncComponent
from .base import BaseStep


@provider("sync_flush_step")
class SyncFlushStep(BaseStep):
    """Push changed tasks; invocation timing belongs to the Job."""

    async def execute(self):
        self.response.answer = await self.component(BaseSyncComponent).flush()
