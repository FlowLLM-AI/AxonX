"""Component contract for replicating workspace task directories to a target service."""

from abc import ABC, abstractmethod

from ...enums import ComponentEnum
from ...task.sync import SyncReport
from ..base import BaseComponent


class BaseSyncComponent(BaseComponent, ABC):
    """Define batched, workspace-backed replication to a configured target service."""

    component_type = ComponentEnum.SYNC

    @abstractmethod
    async def flush(self) -> SyncReport:
        """Replicate the changes queued since the last flush and report the outcome."""
