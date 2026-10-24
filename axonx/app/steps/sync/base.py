"""Dependency declarations for synchronization Steps."""

from abc import ABC

from ...components.types import ComponentEnum
from ..base import BaseStep
from ..task.base import TaskRepositoryStep

__all__ = ["SyncBackendStep", "TaskRepositoryStep"]


class SyncBackendStep(BaseStep, ABC):
    """A Step that drives one configured sync backend."""

    component_domains = (ComponentEnum.SYNC,)
