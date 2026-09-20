"""Build application-local registries from declared AxonX providers."""

from .components.registry import ProviderRegistry, builtin_providers


def create_builtin_registry() -> ProviderRegistry:
    """Build a fresh registry containing every provider shipped with AxonX."""
    registry = ProviderRegistry()
    for implementation in builtin_providers():
        registry.add(implementation)
    return registry
