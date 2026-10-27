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
        self._finalized = False

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

    def _require_composing(self) -> None:
        if self._finalized:
            raise RuntimeError("Application context is already finalized")

    def _set_component_group(
        self,
        category: str,
        components: Mapping[str, BaseComponent],
    ) -> None:
        self._require_composing()
        self._components[category] = MappingProxyType(dict(components))

    def _set_jobs(self, jobs: Mapping[str, BaseJob]) -> None:
        self._require_composing()
        self._jobs.update(jobs)

    def _set_service(self, service: BaseService) -> None:
        self._require_composing()
        self.service = service

    def finalize(self) -> None:
        """Seal the provider registry after composition completes."""
        self._require_composing()
        self.registry.freeze()
        self._finalized = True
