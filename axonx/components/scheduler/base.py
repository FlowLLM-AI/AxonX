"""Scheduler component contract."""

from abc import ABC, abstractmethod

from ...enums import ComponentEnum
from ..base import BaseComponent


class BaseScheduler(BaseComponent, ABC):
    """Trigger Jobs independently of their execution implementation."""

    component_type = ComponentEnum.SCHEDULER

    @abstractmethod
    def describe(self) -> dict:
        """Return the schedule configuration and current trigger status."""
        raise NotImplementedError
