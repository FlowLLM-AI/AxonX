"""Application-scoped runtime state."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from ..components.client.remote import RemotePreflight
from ..config import ApplicationConfig
from .dispatch import JobDispatcher

if TYPE_CHECKING:
    from ..components.base import BaseComponent
    from ..components.job.base import BaseJob
    from ..components.registry import ProviderRegistry
    from ..components.scheduler.base import BaseScheduler
    from ..components.service.base import BaseService


class ApplicationContext:
    """Expose application-scoped runtime state through stable read-only views."""

    def __init__(
        self,
        registry: ProviderRegistry,
        app_config: ApplicationConfig | None = None,
        *,
        remote_preflight: RemotePreflight | None = None,
        **config: Any,
    ) -> None:
        if app_config is not None and config:
            raise TypeError("Pass either app_config or configuration values, not both")
        self.registry = registry
        self.app_config = app_config if app_config is not None else ApplicationConfig(**config)
        self._components: dict[str, Mapping[str, BaseComponent]] = {}
        self._jobs: dict[str, BaseJob] = {}
        self._schedulers: dict[str, BaseScheduler] = {}
        self._components_view = MappingProxyType(self._components)
        self._jobs_view = MappingProxyType(self._jobs)
        self._schedulers_view = MappingProxyType(self._schedulers)
        self.service: BaseService | None = None
        self.metadata: dict[str, Any] = {}
        self.dispatcher = JobDispatcher(self, remote_preflight=remote_preflight)
        self._finalized = False

    @property
    def components(self) -> Mapping[str, Mapping[str, BaseComponent]]:
        return self._components_view

    @property
    def jobs(self) -> Mapping[str, BaseJob]:
        return self._jobs_view

    @property
    def schedulers(self) -> Mapping[str, BaseScheduler]:
        return self._schedulers_view

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

    def _set_schedulers(self, schedulers: Mapping[str, BaseScheduler]) -> None:
        self._require_composing()
        self._schedulers.update(schedulers)

    def _set_service(self, service: BaseService) -> None:
        self._require_composing()
        self.service = service

    def finalize(self) -> None:
        """Seal the provider registry after composition completes."""
        self._require_composing()
        self.registry.freeze()
        self._finalized = True
