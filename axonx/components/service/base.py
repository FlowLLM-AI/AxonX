"""Component contract for remotely callable services."""

from abc import ABC, abstractmethod
from typing import Any

from ...enums import ComponentEnum
from ..base import BaseComponent


class BaseService(BaseComponent, ABC):
    """Define construction and execution of an application service."""

    component_type = ComponentEnum.SERVICE

    @abstractmethod
    def build_service(self, app) -> Any:
        """Build the service application without starting it."""

    @abstractmethod
    def run_app(self, app) -> None:
        """Run the service application until shutdown."""
