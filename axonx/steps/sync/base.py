"""Dependency declarations for synchronization Steps."""

from ...enums import ComponentEnum
from ..base import BaseStep


class SyncBackendStep(BaseStep):
    """A Step that drives one configured sync backend."""

    component_domains = (ComponentEnum.SYNC,)


class TaskRepositoryStep(BaseStep):
    """A Step that applies changes through one task repository."""

    component_domains = (ComponentEnum.TASK_REPOSITORY,)
