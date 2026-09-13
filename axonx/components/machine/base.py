"""Component contract for machine resource inspection."""

from abc import ABC, abstractmethod
from typing import Any

from ...enums import ComponentEnum
from ..base import BaseComponent


class BaseMachineComponent(BaseComponent, ABC):
    """Define local machine resource inspection."""

    component_type = ComponentEnum.MACHINE

    @abstractmethod
    async def get_info(self) -> dict[str, Any]:
        """Return local machine status."""
