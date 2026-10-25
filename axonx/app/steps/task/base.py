"""Shared dependency declaration for Task index Steps."""

from abc import ABC

from ...components.component_type import ComponentType
from ..base import BaseStep


class TaskIndexStep(BaseStep, ABC):
    """A Step that reads one configured Task index."""

    component_domains = (ComponentType.TASK_INDEX,)
