"""Plugin steps."""

from .inspect_plugin import InspectPluginStep
from .install_plugin import InstallPluginStep
from .list_plugins import ListPluginsStep
from .uninstall_plugin import UninstallPluginStep

__all__ = [
    "InspectPluginStep",
    "InstallPluginStep",
    "ListPluginsStep",
    "UninstallPluginStep",
]
