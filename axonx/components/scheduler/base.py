"""Scheduler component contract."""

from abc import ABC, abstractmethod

from ...enums import ComponentEnum
from ..base import BaseComponent


class BaseScheduler(BaseComponent, ABC):
    """Trigger Jobs independently of their execution implementation."""

    component_type = ComponentEnum.SCHEDULER

    @abstractmethod
    def describe(self, *, include_history: bool = False, history_limit: int = 20) -> dict:
        """Return configuration/status, optionally including bounded recent history."""
        raise NotImplementedError
