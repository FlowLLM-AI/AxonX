"""Shared dependency declaration for task-manager Steps."""

from ...enums import ComponentEnum
from ..base import BaseStep


class TaskManagerStep(BaseStep):
    """A Step that drives one configured task manager."""

    component_domains = (ComponentEnum.TASK_MANAGER,)
