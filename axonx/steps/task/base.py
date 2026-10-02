"""Shared dependency declaration for task-manager Steps."""

from abc import ABC

from ...enums import ComponentEnum
from ..base import BaseStep


class TaskManagerStep(BaseStep, ABC):
    """A Step that drives one configured task manager."""

    component_domains = (ComponentEnum.TASK_MANAGER,)
