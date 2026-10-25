"""Component contract for remotely callable services."""

from abc import ABC, abstractmethod
from typing import Any

from ..base import BaseComponent
from ..component_type import ComponentType


class BaseService(BaseComponent, ABC):
    """Define construction and execution of an application service."""

    component_type = ComponentType.SERVICE

    @abstractmethod
    def build_service(self, app) -> Any:
        """Build the service application without starting it."""

    @abstractmethod
    def run_app(self, app) -> None:
        """Run the service application until shutdown."""
