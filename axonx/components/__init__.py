"""Core component lifecycle types and the built-in registry."""

from .base_component import BaseComponent
from .component_mixin import ComponentMixin
from .component_registry import R, ComponentRegistry
from .machine_component import MachineComponent
from .plugin_component import PluginComponent

__all__ = [
    "BaseComponent",
    "ComponentMixin",
    "ComponentRegistry",
    "MachineComponent",
    "PluginComponent",
    "R",
]
