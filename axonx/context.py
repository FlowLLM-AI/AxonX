"""Application- and invocation-scoped shared state."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .schema import ApplicationConfig, Response

if TYPE_CHECKING:
    from .components.base import BaseComponent
    from .components.job.base import BaseJob
    from .components.registry import ComponentRegistry


class ApplicationContext:
    """Hold shared state for every component in one application instance."""

    def __init__(self, registry: ComponentRegistry, **config: Any) -> None:
        self.registry = registry
        self.app_config = ApplicationConfig(**config)
        self.components: dict[str, dict[str, BaseComponent]] = {}
        self.jobs: dict[str, BaseJob] = {}
        self.metadata: dict[str, Any] = {}


class RuntimeContext(dict):
    """Share invocation data and the response across one job's steps."""

    def __init__(self, **data: Any) -> None:
        super().__init__(data)
        self.response = Response()
