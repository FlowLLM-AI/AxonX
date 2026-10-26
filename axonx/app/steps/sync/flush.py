"""Flush changes queued by a workspace sync component."""

from ...components.component_type import ComponentType
from ...registry import provider
from ..base import BaseStep


@provider("sync_flush_step")
class SyncFlushStep(BaseStep):
    """Run one bounded sync round; scheduling remains configuration policy."""

    component_domains = (ComponentType.SYNC,)

    async def execute(self):
        self.response.answer = await self.sync.flush()
