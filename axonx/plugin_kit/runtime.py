"""Load plugin providers into one application-local registry."""

from pathlib import Path
from types import ModuleType

from ..components.base import BaseComponent
from ..components.registry import ProviderRegistry
from ..config import ApplicationConfig, JobConfig
from ..enums import component_type_name
from .contributions import index_contributions
from .discovery import list_installed_plugins
from .installer import ensure_plugin_sources
from .loading import load_symbol


def load_plugin_providers(
    config: ApplicationConfig,
    registry: ProviderRegistry,
) -> dict[str, JobConfig]:
    """Prepare plugin sources, register providers, and return contributed Jobs."""
    artifact_directory = Path(config.workspace_dir).expanduser() / "plugins" / "artifacts"
    plugins = (
        ensure_plugin_sources(config.plugins.sources, artifact_directory)
        if config.plugins.sources
        else list_installed_plugins()
    )
    contributions = index_contributions(plugins)

    modules: dict[str, ModuleType] = {}
    for component_type, backends in contributions.components.items():
        for backend, target in backends.items():
            implementation = load_symbol(
                target,
                BaseComponent,
                kind="Component",
                modules=modules,
            )
            actual_type = component_type_name(implementation.component_type)
            if actual_type != component_type:
                raise TypeError(
                    f"Component target {target} declares type {actual_type!r}, "
                    f"expected {component_type!r}",
                )
            registry.add(
                implementation,
                name=backend,
                owner=contributions.component_owners[(component_type, backend)],
            )
    return contributions.jobs
