"""Component contract for machine resource inspection."""

from abc import ABC, abstractmethod
from typing import Any

from ...enumeration import ComponentEnum
from ..base_component import BaseComponent


class BaseMachineComponent(BaseComponent, ABC):
    """Define local or remote machine resource inspection."""

    component_type = ComponentEnum.MACHINE

    @abstractmethod
    async def get_info(self, address: str | None = None) -> dict[str, Any]:
        """Return local status, or status from one configured remote node."""
