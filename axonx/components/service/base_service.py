"""Abstract interface for services that expose an AxonX application."""

from abc import ABC, abstractmethod

from ...enumeration import ComponentEnum
from ..base_component import BaseComponent


class BaseService(BaseComponent, ABC):
    """Define how a service runs an application."""

    component_type = ComponentEnum.SERVICE

    @abstractmethod
    def run_app(self, app):
        """Run the service until its server exits."""
