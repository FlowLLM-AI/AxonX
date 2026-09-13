"""Plugin component contracts and built-in implementations."""

from .base import BasePluginComponent
from .local import LocalPluginComponent

__all__ = ["BasePluginComponent", "LocalPluginComponent"]
