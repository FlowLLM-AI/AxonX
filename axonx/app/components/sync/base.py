"""Component contract for replicating workspace task directories to a target service."""

from abc import ABC, abstractmethod

from ..base import BaseComponent
from ..component_type import ComponentType
from .models import SyncReport


class BaseSyncComponent(BaseComponent, ABC):
    """Define batched, workspace-backed replication to a configured target service."""

    component_type = ComponentType.SYNC

    @abstractmethod
    async def flush(self) -> SyncReport:
        """Replicate locally observed changes after initial target reconciliation."""
