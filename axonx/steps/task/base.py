"""Shared dependency declaration for Task repository Steps."""

from abc import ABC

from ...enums import ComponentEnum
from ..base import BaseStep


class TaskRepositoryStep(BaseStep, ABC):
    """A Step that reads one configured Task repository."""

    component_domains = (ComponentEnum.TASK_REPOSITORY,)
