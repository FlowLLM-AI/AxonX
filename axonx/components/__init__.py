"""Core component lifecycle types and the built-in registry."""

from .base_component import BaseComponent
from .component_mixin import ComponentMixin
from .component_registry import R, ComponentRegistry
from .http_service import BaseService, HttpService
from .machine_component import BaseMachineComponent, LocalMachineComponent, MachineComponent
from .plugin_component import BasePluginComponent, LocalPluginComponent, PluginComponent

__all__ = [
    "BaseComponent",
    "BaseMachineComponent",
    "BasePluginComponent",
    "BaseService",
    "ComponentMixin",
    "ComponentRegistry",
    "HttpService",
    "LocalMachineComponent",
    "LocalPluginComponent",
    "MachineComponent",
    "PluginComponent",
    "R",
]
