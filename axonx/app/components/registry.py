"""Explicit provider declarations and application-local provider lookup."""

from __future__ import annotations

from collections.abc import Iterable
from typing import cast

from .base import Component

_PROVIDER_NAME = "__axonx_provider_name__"


def provider(name: str):
    """Declare a provider name without changing any registry."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Provider name must be a non-empty string")

    def decorate[ProviderT: type](cls: ProviderT) -> ProviderT:
        if _PROVIDER_NAME in cls.__dict__:
            raise TypeError(f"{cls.__name__} already declares a provider name")
        setattr(cls, _PROVIDER_NAME, name)
        return cls

    return decorate


class ProviderRegistry:
    """Application-local mapping from ``(component type, backend)`` to a class."""

    def __init__(self, implementations: Iterable[type[Component]] = ()) -> None:
        self._providers: dict[tuple[str, str], type[Component]] = {}
        self._frozen = False
        for implementation in implementations:
            self.add(implementation)

    def add(self, implementation: type[Component]) -> None:
        """Add one declared provider and reject conflicting implementations."""
        if self._frozen:
            raise RuntimeError("Provider registry is frozen")
        if not isinstance(implementation, type) or not issubclass(implementation, Component):
            raise TypeError("Provider implementation must subclass Component")

        component_type = implementation.component_type
        if not isinstance(component_type, str) or not component_type.strip():
            raise TypeError(f"{implementation.__name__} must declare a non-empty component_type")
        provider_name = implementation.__dict__.get(_PROVIDER_NAME)
        if not isinstance(provider_name, str) or not provider_name:
            raise TypeError(f"{implementation.__name__} must be decorated with @provider(name)")
        key = (component_type, provider_name)
        existing = self._providers.get(key)
        if existing is not None and existing is not implementation:
            raise ValueError(
                f"Provider '{component_type}:{provider_name}' is supplied by both "
                f"'{existing.__module__}.{existing.__qualname__}' and "
                f"'{implementation.__module__}.{implementation.__qualname__}'",
            )
        self._providers[key] = implementation

    def require[T: Component](
        self,
        component_type: str,
        name: str,
        expected_base: type[T],
    ) -> type[T]:
        """Resolve and type-check one provider or raise a configuration error."""
        implementation = self._providers.get((component_type, name))
        if implementation is None:
            raise ValueError(f"Unknown {component_type} backend: {name}")
        if not issubclass(implementation, expected_base):
            raise TypeError(
                f"Provider {component_type}:{name} must subclass {expected_base.__name__}",
            )
        return cast(type[T], implementation)

    def freeze(self) -> None:
        """Prevent further mutation after application composition."""
        self._frozen = True

    @property
    def frozen(self) -> bool:
        return self._frozen
