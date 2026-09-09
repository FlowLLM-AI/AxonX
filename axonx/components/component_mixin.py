"""Shared context and component access for components and steps."""

from pathlib import Path

from ..enumeration import ComponentEnum, component_type_name
from ..utils import get_logger


class ComponentMixin:
    """Attach component identity, logging, context, and dependency lookup."""

    component_type = ComponentEnum.BASE

    def __init__(self, name=None, backend="", app_context=None, **kwargs):
        self.name = name or type(self).__name__
        self.backend = backend
        self.app_context = app_context
        self.kwargs = kwargs
        self.logger = get_logger(self.name)

    @property
    def workspace_path(self) -> Path:
        """Return the configured workspace or the current directory."""
        if self.app_context is None:
            return Path.cwd()
        return Path(self.app_config.workspace_dir).expanduser()

    @property
    def app_config(self):
        """Return the shared application configuration."""
        if self.app_context is None:
            raise RuntimeError("Application config requires an application context")
        return self.app_context.app_config

    def get_component(self, component_type, name="default"):
        """Look up a component instance from the application context."""
        if self.app_context is None:
            raise RuntimeError("Component access requires an application context")
        return self.app_context.components[component_type_name(component_type)][name]
