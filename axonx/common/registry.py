"""Explicit provider declarations and application-local provider lookup."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from types import MappingProxyType
from typing import cast


def component_type_name(value: str) -> str:
    """Normalize a component enum or non-empty string to its string name."""
    if not isinstance(value, str) or not value:
        raise ValueError("Component type must be a non-empty string")
    return str(value)


_PROVIDER_NAME = "__axonx_provider_name__"


def provider(name: str):
    """Declare a provider name without changing any registry."""
    if not isinstance(name, str) or not name:
        raise ValueError("Provider name must be a non-empty string")

    def decorate[ProviderT: type](cls: ProviderT) -> ProviderT:
        if _PROVIDER_NAME in cls.__dict__:
            raise TypeError(f"{cls.__name__} already declares a provider name")
        setattr(cls, _PROVIDER_NAME, name)
        return cls

    return decorate


def declared_provider_name(cls: type) -> str:
    """Return the backend name explicitly declared on ``cls``."""
    name = cls.__dict__.get(_PROVIDER_NAME)
    if not isinstance(name, str) or not name:
        raise TypeError(f"{cls.__name__} must be decorated with @provider(name)")
    return name


class ProviderRegistry:
    """Application-local mapping from ``(component type, backend)`` to a class."""

    def __init__(self, implementations: Iterable[type] = ()) -> None:
        self._providers: dict[tuple[str, str], type] = {}
        self._frozen = False
        for implementation in implementations:
            self.add(implementation)

    def add(self, implementation: type) -> None:
        """Add one declared provider and reject conflicting implementations."""
        if self._frozen:
            raise RuntimeError("Provider registry is frozen")
        if not isinstance(implementation, type):
            raise TypeError("Provider implementation must be a class")

        component_type = component_type_name(getattr(implementation, "component_type", None))
        provider_name = declared_provider_name(implementation)
        key = (component_type, provider_name)
        existing = self._providers.get(key)
        if existing is not None and existing is not implementation:
            raise ValueError(
                f"Provider '{component_type}:{provider_name}' is supplied by both "
                f"'{existing.__module__}.{existing.__qualname__}' and "
                f"'{implementation.__module__}.{implementation.__qualname__}'",
            )
        self._providers[key] = implementation

    def require[T](
        self,
        component_type: str,
        name: str,
        expected_base: type[T],
    ) -> type[T]:
        """Resolve and type-check one provider or raise a configuration error."""
        normalized_type = component_type_name(component_type)
        implementation = self._providers.get((normalized_type, name))
        if implementation is None:
            raise ValueError(f"Unknown {normalized_type} backend: {name}")
        if not issubclass(implementation, expected_base):
            raise TypeError(
                f"Provider {normalized_type}:{name} must subclass {expected_base.__name__}",
            )
        return cast(type[T], implementation)

    def get_all[T](
        self,
        component_type: str,
        expected_base: type[T],
    ) -> dict[str, type[T]]:
        """Return all type-checked implementations in one component domain."""
        normalized_type = component_type_name(component_type)
        return {
            name: self.require(normalized_type, name, expected_base)
            for provider_type, name in self._providers
            if provider_type == normalized_type
        }

    def freeze(self) -> None:
        """Prevent further mutation after application composition."""
        self._frozen = True

    @property
    def frozen(self) -> bool:
        return self._frozen

    @property
    def providers(self) -> Mapping[tuple[str, str], type]:
        """Expose a read-only provider index for diagnostics."""
        return MappingProxyType(self._providers)
