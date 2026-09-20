"""Application-scoped runtime state."""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING

from ..config import ApplicationConfig
from .dispatch import JobDispatcher
from .remote import RemotePreflight

if TYPE_CHECKING:
    from ..components.base import BaseComponent
    from ..components.job.base import BaseJob
    from ..components.registry import ProviderRegistry
    from ..components.scheduler.base import BaseScheduler
    from ..components.service.base import BaseService


class ApplicationContext:
    """Build mutable runtime state, then expose it read-only after composition."""

    def __init__(self, registry: ProviderRegistry, **config) -> None:
        self.registry = registry
        self.app_config = ApplicationConfig(**config)
        self.components: dict[str, dict[str, BaseComponent]] = {}
        self.jobs: dict[str, BaseJob] = {}
        self.schedulers: dict[str, BaseScheduler] = {}
        self.service: BaseService | None = None
        self.metadata: dict = {}
        self.dispatcher: JobDispatcher
        self._finalized = False

    def finalize(self, *, remote_preflight: RemotePreflight | None = None) -> None:
        """Seal provider and runtime indexes and attach shared services."""
        if self._finalized:
            raise RuntimeError("Application context is already finalized")
        self.registry.freeze()
        self.components = MappingProxyType(
            {
                category: MappingProxyType(dict(group))
                for category, group in self.components.items()
            }
        )
        self.jobs = MappingProxyType(dict(self.jobs))
        self.schedulers = MappingProxyType(dict(self.schedulers))
        self.dispatcher = JobDispatcher(self, remote_preflight=remote_preflight)
        self._finalized = True
