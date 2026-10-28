"""Application-scoped runtime state."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from ..config.models import ApplicationConfig
from ..workspace.core import Workspace
from .dispatch import JobDispatcher

if TYPE_CHECKING:
    from ...task.runtime.catalog import TaskCatalog
    from ..components.base import BaseComponent
    from ..components.job.base import BaseJob
    from ..components.registry import ProviderRegistry
    from ..components.service.base import BaseService
    from ..components.updater.base import UpdateBackend


class ApplicationContext:
    """Expose application-scoped runtime state through stable read-only views."""

    def __init__(
        self,
        registry: ProviderRegistry,
        app_config: ApplicationConfig,
        workspace: Workspace | None = None,
        updates: UpdateBackend | None = None,
        task_catalog: TaskCatalog | None = None,
    ) -> None:
        self.registry = registry
        self.app_config = app_config
        self.updates = updates
        self._task_catalog = task_catalog
        self.workspace = workspace or Workspace(
            self.app_config.workspace_dir,
            transfer_budget_bytes=self.app_config.transfer_budget_bytes,
        )
        self._components: dict[str, Mapping[str, BaseComponent]] = {}
        self._jobs: dict[str, BaseJob] = {}
        self._components_view = MappingProxyType(self._components)
        self._jobs_view = MappingProxyType(self._jobs)
        self.service: BaseService | None = None
        self.metadata: dict[str, Any] = {}
        self.dispatcher = JobDispatcher(self)

    @property
    def task_catalog(self) -> TaskCatalog:
        """Return the Task directory supplied by the application host."""
        if self._task_catalog is None:
            raise RuntimeError("No Task catalog is configured")
        return self._task_catalog

    @property
    def components(self) -> Mapping[str, Mapping[str, BaseComponent]]:
        return self._components_view

    @property
    def jobs(self) -> Mapping[str, BaseJob]:
        return self._jobs_view

    def finalize(
        self,
        components: Mapping[str, Mapping[str, BaseComponent]],
        jobs: Mapping[str, BaseJob],
        service: BaseService | None,
    ) -> None:
        """Publish the complete runtime once and seal its provider registry."""
        if self.registry.frozen:
            raise RuntimeError("Application context is already finalized")
        self._components.update({category: MappingProxyType(dict(group)) for category, group in components.items()})
        self._jobs.update(jobs)
        self.service = service
        self.registry.freeze()
