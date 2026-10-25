"""Context-bound objects and managed asynchronous components."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from .component_type import ComponentType
from ..config.models import ApplicationConfig
from ...common.logging import get_logger
from ...common.registry import component_type_name
from ...common.workspace import Workspace

if TYPE_CHECKING:
    from ..core.context import ApplicationContext


class ComponentBase:
    """Common identity, configuration, logging, and application access."""

    component_type = ComponentType.BASE
    component_domains: ClassVar[tuple[ComponentType, ...]] = ()

    def __init__(
        self,
        name: str | None = None,
        backend: str = "",
        app_context: ApplicationContext | None = None,
        **kwargs,
    ) -> None:
        self.name = name or type(self).__name__
        self.backend = backend
        self.app_context = app_context
        self.kwargs = kwargs
        self._component_names = {domain: self.kwargs.pop(domain.value, "default") for domain in self.component_domains}
        self.logger = get_logger(self.name)

    @property
    def workspace(self) -> Workspace:
        return self._require_context().workspace

    @property
    def workspace_path(self) -> Path:
        return self.workspace.root

    @property
    def app_config(self) -> ApplicationConfig:
        return self._require_context().app_config

    def get_component(self, component_type, name: str = "default"):
        return self._require_context().components[component_type_name(component_type)][name]

    def _require_context(self) -> ApplicationContext:
        if self.app_context is None:
            raise RuntimeError(f"{self.name} requires an application context")
        return self.app_context


@dataclass(frozen=True, slots=True)
class DependencySpec:
    """A component attribute that must be injected before startup."""

    attribute: str
    component_type: str
    name: str
    required: bool
    expected_type: type[BaseComponent]


class BaseComponent(ComponentBase):
    """Provide deterministic dependency injection and asynchronous lifecycle."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.is_started = False
        self._lifecycle_lock = asyncio.Lock()
        self._dependencies: dict[str, DependencySpec] = {}

    def depend(
        self,
        attribute: str,
        name: str | None,
        base_cls: type[BaseComponent],
        *,
        required: bool = True,
    ) -> None:
        """Declare an attribute that the application graph must inject."""
        if not isinstance(attribute, str) or not attribute.isidentifier():
            raise ValueError(f"Invalid dependency attribute: {attribute!r}")
        if attribute in self._dependencies:
            raise ValueError(f"Dependency attribute already declared: {attribute}")
        if not name:
            if required:
                raise ValueError(f"Dependency {attribute!r} requires a component name")
            setattr(self, attribute, None)
            return
        component_type = component_type_name(base_cls.component_type)
        if component_type == ComponentType.BASE.value:
            raise TypeError(f"{base_cls.__name__} must declare a non-BASE component_type")
        self._dependencies[attribute] = DependencySpec(
            attribute=attribute,
            component_type=component_type,
            name=name,
            required=required,
            expected_type=base_cls,
        )

    @property
    def dependencies(self) -> tuple[DependencySpec, ...]:
        return tuple(self._dependencies.values())

    async def start(self) -> None:
        """Start once, preserving both startup and rollback failures."""
        async with self._lifecycle_lock:
            if self.is_started:
                return
            try:
                await self._start()
            except BaseException as start_error:
                try:
                    await self._close()
                except BaseException as cleanup_error:  # noqa: BLE001 - preserve rollback failure.
                    raise BaseExceptionGroup(
                        f"{self.name} startup failed and rollback was incomplete",
                        [start_error, cleanup_error],
                    ) from None
                raise
            self.is_started = True

    async def close(self) -> None:
        """Close once after a successful start."""
        async with self._lifecycle_lock:
            if not self.is_started:
                return
            try:
                await self._close()
            finally:
                self.is_started = False

    async def _start(self) -> None:
        pass

    async def _close(self) -> None:
        pass

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *_):
        await self.close()
