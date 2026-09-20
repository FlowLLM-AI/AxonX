"""Explicit provider declarations and application-local provider lookup."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Self, TypeVar, cast

from ..enums import ComponentType, component_type_name

ProviderT = TypeVar("ProviderT", bound=type)
_PROVIDER_NAME = "__axonx_provider_name__"
_BUILTIN_PROVIDERS: dict[tuple[str, str], type] = {}


def provider(name: str):
    """Declare and register a built-in provider implementation."""
    if not isinstance(name, str) or not name:
        raise ValueError("Provider name must be a non-empty string")

    def decorate(cls: ProviderT) -> ProviderT:
        if _PROVIDER_NAME in cls.__dict__:
            raise TypeError(f"{cls.__name__} already declares a provider name")
        setattr(cls, _PROVIDER_NAME, name)
        if cls.__module__ == "axonx" or cls.__module__.startswith("axonx."):
            _BUILTIN_PROVIDERS[(cls.__module__, cls.__qualname__)] = cls
        return cls

    return decorate


def builtin_providers() -> tuple[type, ...]:
    """Return provider classes registered by imported AxonX modules."""
    return tuple(_BUILTIN_PROVIDERS.values())


def declared_provider_name(cls: type) -> str:
    """Return the backend name explicitly declared on ``cls``."""
    name = cls.__dict__.get(_PROVIDER_NAME)
    if not isinstance(name, str) or not name:
        raise TypeError(f"{cls.__name__} must be decorated with @provider(name)")
    return name


@dataclass(frozen=True, slots=True)
class Provider:
    """One uniquely owned provider implementation."""

    component_type: str
    name: str
    implementation: type
    owner: str


class ProviderRegistry:
    """Application-local mapping from ``(component type, backend)`` to a class."""

    def __init__(self) -> None:
        self._providers: dict[tuple[str, str], Provider] = {}
        self._frozen = False

    @classmethod
    def from_builtins(cls) -> Self:
        """Build a fresh registry from every imported built-in provider."""
        registry = cls()
        for implementation in builtin_providers():
            registry.add(implementation)
        return registry

    def add(
        self,
        implementation: type,
        *,
        name: str | None = None,
        owner: str | None = None,
    ) -> None:
        """Add one provider and reject ambiguous ownership."""
        if self._frozen:
            raise RuntimeError("Provider registry is frozen")
        if not isinstance(implementation, type):
            raise TypeError("Provider implementation must be a class")

        component_type = component_type_name(
            getattr(implementation, "component_type", None)
        )
        provider_name = declared_provider_name(implementation) if name is None else name
        if not isinstance(provider_name, str) or not provider_name:
            raise ValueError("Provider name must be a non-empty string")

        key = (component_type, provider_name)
        provider_owner = owner or implementation.__module__
        existing = self._providers.get(key)
        if existing is not None:
            if (
                existing.implementation is implementation
                and existing.owner == provider_owner
            ):
                return
            raise ValueError(
                f"Provider '{component_type}:{provider_name}' is supplied by both "
                f"'{existing.owner}' and '{provider_owner}'",
            )
        self._providers[key] = Provider(
            component_type=component_type,
            name=provider_name,
            implementation=implementation,
            owner=provider_owner,
        )

    def require[T](
        self,
        component_type: ComponentType,
        name: str,
        expected_base: type[T],
    ) -> type[T]:
        """Resolve and type-check one provider or raise a configuration error."""
        normalized_type = component_type_name(component_type)
        provider = self._providers.get((normalized_type, name))
        if provider is None:
            raise ValueError(f"Unknown {normalized_type} backend: {name}")
        implementation = provider.implementation
        if not issubclass(implementation, expected_base):
            raise TypeError(
                f"Provider {normalized_type}:{name} must subclass "
                f"{expected_base.__name__}",
            )
        return cast(type[T], implementation)

    def get_all[T](
        self,
        component_type: ComponentType,
        expected_base: type[T],
    ) -> dict[str, type[T]]:
        """Return all type-checked implementations in one component domain."""
        normalized_type = component_type_name(component_type)
        implementations: dict[str, type[T]] = {}
        for (provider_type, name), item in self._providers.items():
            if provider_type != normalized_type:
                continue
            implementation = item.implementation
            if not issubclass(implementation, expected_base):
                raise TypeError(
                    f"Provider {provider_type}:{name} must subclass "
                    f"{expected_base.__name__}",
                )
            implementations[name] = cast(type[T], implementation)
        return implementations

    def freeze(self) -> None:
        """Prevent further mutation after application composition."""
        self._frozen = True

    @property
    def frozen(self) -> bool:
        return self._frozen

    @property
    def providers(self) -> Mapping[tuple[str, str], Provider]:
        """Expose a read-only provider index for diagnostics."""
        return MappingProxyType(self._providers)
