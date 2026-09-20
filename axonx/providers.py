"""Build application-local registries from decorated AxonX providers."""

from .components.registry import ProviderRegistry, builtin_providers


def create_builtin_registry() -> ProviderRegistry:
    """Build a fresh registry containing every imported built-in provider."""
    registry = ProviderRegistry()
    for implementation in builtin_providers():
        registry.add(implementation)
    return registry
