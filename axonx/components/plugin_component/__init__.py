"""Plugin component contracts and built-in implementations."""

from .base_plugin_component import BasePluginComponent
from .local_plugin_component import LocalPluginComponent

# Backward-compatible name for the original built-in implementation.
PluginComponent = LocalPluginComponent

__all__ = ["BasePluginComponent", "LocalPluginComponent", "PluginComponent"]
