"""Scheduler component contract."""

from abc import ABC

from ...enums import ComponentEnum
from ..base import BaseComponent


class BaseScheduler(BaseComponent, ABC):
    """Trigger Jobs independently of their execution implementation."""

    component_type = ComponentEnum.SCHEDULER
