"""Shared component context, dependency declarations, and managed lifecycle."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Self

from ...utils.logging import get_logger

if TYPE_CHECKING:
    from ..config.models import ApplicationConfig
    from ..core.context import ApplicationContext
    from ..workspace.core import Workspace


class Component:
    """Common identity, configuration, logging, and application access."""

    component_type: ClassVar[str] = ""

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

    def _require_context(self) -> ApplicationContext:
        if self.app_context is None:
            raise RuntimeError(f"{self.name} requires an application context")
        return self.app_context


@dataclass(frozen=True, slots=True)
class Dependency:
    """An attribute supplied by a named component of the expected base type."""

    attribute: str
    name: str | None
    expected_type: type[BaseComponent]
    required: bool

    @property
    def component_type(self) -> str:
        """Use the expected base type as the single source of the category."""
        return self.expected_type.component_type


class BaseComponent(Component):
    """Provide deterministic dependency injection and asynchronous lifecycle."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.is_started = False
        self._lifecycle_lock = asyncio.Lock()
        self._dependencies: dict[str, Dependency] = {}

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
        if not isinstance(base_cls, type) or not issubclass(base_cls, BaseComponent):
            raise TypeError("Dependency base must subclass BaseComponent")
        if not isinstance(base_cls.component_type, str) or not base_cls.component_type.strip():
            raise TypeError(f"{base_cls.__name__} must declare a non-empty component_type")
        if name is not None and (not isinstance(name, str) or not name.strip()):
            raise ValueError("Dependency name must be a non-empty string or None")
        if not name:
            if required:
                raise ValueError(f"Dependency {attribute!r} requires a component name")
            setattr(self, attribute, None)
        self._dependencies[attribute] = Dependency(
            attribute=attribute,
            name=name,
            required=required,
            expected_type=base_cls,
        )

    @property
    def dependencies(self) -> tuple[Dependency, ...]:
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

    async def __aenter__(self) -> Self:
        await self.start()
        return self

    async def __aexit__(self, *_) -> None:
        await self.close()
