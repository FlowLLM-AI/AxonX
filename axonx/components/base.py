"""Asynchronous component lifecycle."""

import asyncio
from typing import Callable, TypeVar, cast

from .mixin import ComponentMixin
from ..enums import ComponentEnum, component_type_name

T = TypeVar("T", bound="BaseComponent")


class Dependency:
    """A named component reference resolved immediately before startup."""

    __slots__ = ("ctype", "name", "default_factory", "optional")

    def __init__(self, ctype, name, default_factory=None, optional=True):
        self.ctype = component_type_name(ctype)
        self.name = name
        self.default_factory = default_factory
        self.optional = optional

    def __getattr__(self, item):
        raise RuntimeError(
            f"Dependency {self.ctype}:{self.name} accessed before start() " f"(attribute {item!r})",
        )


class BaseComponent(ComponentMixin):
    """Provide idempotent, concurrency-safe asynchronous lifecycle methods."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.is_started = False
        self._lifecycle_lock = asyncio.Lock()
        self._binding_specs: dict[str, Dependency] = {}
        self._owned_components: list[BaseComponent] = []

    @staticmethod
    def bind(
        name: str | None,
        base_cls: type[T],
        *,
        default_factory: Callable[[], T] | None = None,
        optional: bool = True,
    ) -> T | None:
        """Declare a dependency on one named component."""
        if not name:
            return None
        ctype = component_type_name(base_cls.component_type)
        if ctype == ComponentEnum.BASE.value:
            raise TypeError(f"{base_cls.__name__} must declare a non-BASE component_type")
        return cast(T, Dependency(ctype, name, default_factory, optional))

    @property
    def dependency_bindings(self) -> dict[str, Dependency]:
        """Return dependency declarations keyed by their bound attribute."""
        bindings = dict(self._binding_specs)
        bindings.update((name, value) for name, value in self.__dict__.items() if isinstance(value, Dependency))
        return bindings

    @property
    def dependencies(self) -> list[Dependency]:
        """Return all dependency declarations for this component."""
        return list(self.dependency_bindings.values())

    async def _resolve_dependencies(self):
        for attribute, dependency in list(self.__dict__.items()):
            if not isinstance(dependency, Dependency):
                continue
            self._binding_specs[attribute] = dependency
            target = None
            if self.app_context is not None:
                target = self.app_context.components.get(dependency.ctype, {}).get(dependency.name)
            elif dependency.default_factory is not None:
                target = dependency.default_factory()
                self._owned_components.append(target)
            if target is None and not dependency.optional:
                raise ValueError(f"Missing component dependency: {dependency.ctype}:{dependency.name}")
            setattr(self, attribute, target)

    @staticmethod
    async def _close_owned(components) -> list[BaseException]:
        errors = []
        for component in reversed(components):
            try:
                await component.close()
            except BaseException as exc:
                errors.append(exc)
        return errors

    async def start(self):
        """Start this component once and clean up a partial failed start."""
        async with self._lifecycle_lock:
            if self.is_started:
                return
            started_owned = []
            start_hook_entered = False
            try:
                await self._resolve_dependencies()
                for component in self._owned_components:
                    await component.start()
                    started_owned.append(component)
                start_hook_entered = True
                await self._start()
            except BaseException:
                if start_hook_entered:
                    # noinspection PyBroadException
                    try:
                        await self._close()
                    except BaseException:
                        self.logger.exception("Startup cleanup failed")
                for error in await self._close_owned(started_owned):
                    self.logger.error(f"Owned component cleanup failed: {error}")
                raise
            self.is_started = True

    async def close(self):
        """Close this component once if it has successfully started."""
        async with self._lifecycle_lock:
            if self.is_started:
                errors = []
                try:
                    await self._close()
                except BaseException as exc:
                    errors.append(exc)
                errors.extend(await self._close_owned(self._owned_components))
                self.is_started = False
                if len(errors) == 1:
                    raise errors[0]
                if errors:
                    raise BaseExceptionGroup("Component cleanup failed", errors)

    async def _start(self):
        pass

    async def _close(self):
        pass

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *_):
        await self.close()
