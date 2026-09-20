"""Plugin artifacts, installed-environment discovery, and lifecycle operations."""

from .contributions import PluginContributions, index_contributions
from .discovery import (
    get_installed_plugin,
    installed_plugin_for_task,
    list_installed_plugins,
)
from .installer import (
    ensure_plugin_sources,
    install_plugin,
    install_staged_plugin,
    prepare_artifact,
    uninstall_plugin,
)
from .manifest import parse_plugin_manifest
from .models import (
    PluginArtifact,
    PluginInfo,
    PluginInstallResult,
    PluginUninstallResult,
)
from .wheel import (
    build_wheel,
    inspect_wheel,
    install_artifact,
    source_sha256,
)

__all__ = [
    "PluginArtifact",
    "PluginContributions",
    "PluginInfo",
    "PluginInstallResult",
    "PluginUninstallResult",
    "build_wheel",
    "ensure_plugin_sources",
    "get_installed_plugin",
    "inspect_wheel",
    "install_plugin",
    "install_artifact",
    "install_staged_plugin",
    "installed_plugin_for_task",
    "index_contributions",
    "list_installed_plugins",
    "parse_plugin_manifest",
    "prepare_artifact",
    "source_sha256",
    "uninstall_plugin",
]
