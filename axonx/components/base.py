"""Context-bound objects and managed asynchronous components."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from ..config import ApplicationConfig
from ..enums import ComponentEnum, component_type_name
from ..utils import get_logger

if TYPE_CHECKING:
    from ..core.context import ApplicationContext


class ComponentBase:
    """Common identity, configuration, logging, and application access."""

    component_type = ComponentEnum.BASE
    component_domains: ClassVar[tuple[ComponentEnum, ...]] = ()

    def __init__(
        self,
        name: str | None = None,
        backend: str = "",
        app_context: ApplicationContext | None = None,
        **options,
    ) -> None:
        self.name = name or type(self).__name__
        self.backend = backend
        self.app_context = app_context
        self.extra_options = options
        self._component_names = {
            domain: self.extra_options.pop(domain.value, "default")
            for domain in self.component_domains
        }
        self.logger = get_logger(self.name)

    @property
    def workspace_path(self) -> Path:
        if self.app_context is None:
            return Path.cwd()
        return Path(self.app_config.workspace_dir).expanduser()

    @property
    def app_config(self) -> ApplicationConfig:
        if self.app_context is None:
            raise RuntimeError("Application config requires an application context")
        return self.app_context.app_config

    def get_component(self, component_type, name: str = "default"):
        if self.app_context is None:
            raise RuntimeError("Component access requires an application context")
        return self.app_context.components[component_type_name(component_type)][name]


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
        if component_type == ComponentEnum.BASE.value:
            raise TypeError(
                f"{base_cls.__name__} must declare a non-BASE component_type"
            )
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

    def inject_dependencies(
        self,
        components: Mapping[tuple[str, str], BaseComponent],
    ) -> None:
        """Bind every declared dependency after graph validation succeeds."""
        for dependency in self._dependencies.values():
            target = components.get((dependency.component_type, dependency.name))
            if target is None and dependency.required:
                raise RuntimeError(
                    "Validated dependency disappeared: "
                    f"{dependency.component_type}:{dependency.name}"
                )
            if target is not None and not isinstance(target, dependency.expected_type):
                raise TypeError(
                    f"Dependency {dependency.component_type}:{dependency.name} must be "
                    f"a {dependency.expected_type.__name__}"
                )
            setattr(self, dependency.attribute, target)

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
