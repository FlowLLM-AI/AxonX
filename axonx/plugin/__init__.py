"""Plugin artifacts, installed-environment discovery, and lifecycle operations."""

from .contributions import PluginContributions, index_contributions
from .discovery import get_installed_plugin, list_installed_plugins
from .installer import install_plugin, prepare_artifact, uninstall_plugin
from .manifest import parse_plugin_manifest
from .models import PluginArtifact, PluginInfo, PluginUninstallResult
from .wheel import build_wheel, inspect_wheel, install_artifact, source_sha256

__all__ = [
    "PluginArtifact",
    "PluginContributions",
    "PluginInfo",
    "PluginUninstallResult",
    "build_wheel",
    "get_installed_plugin",
    "inspect_wheel",
    "install_plugin",
    "install_artifact",
    "index_contributions",
    "list_installed_plugins",
    "parse_plugin_manifest",
    "prepare_artifact",
    "source_sha256",
    "uninstall_plugin",
]
