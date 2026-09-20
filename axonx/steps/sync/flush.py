"""Flush changes queued by a workspace sync component."""

from ...components.registry import provider
from .base import SyncBackendStep


@provider("sync_flush_step")
class SyncFlushStep(SyncBackendStep):
    """Run one bounded sync round; scheduling remains configuration policy."""

    async def execute(self):
        self.response.answer = await self.sync.flush()
