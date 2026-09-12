"""Component contract for plugin lifecycle and Task lookup."""

from abc import ABC, abstractmethod
from pathlib import Path

from ...enumeration import ComponentEnum
from ...plugin.artifact import PluginArtifact
from ..base_component import BaseComponent


class BasePluginComponent(BaseComponent, ABC):
    """Define operations for preparing plugins and resolving their Tasks."""

    component_type = ComponentEnum.PLUGIN

    @abstractmethod
    def prepare(self, source: Path) -> PluginArtifact:
        """Prepare a plugin source tree and publish its Tasks."""

    @abstractmethod
    def install_wheel(self, data: bytes, expected_sha256: str, filename: str) -> PluginArtifact:
        """Validate and install an uploaded wheel."""

    @abstractmethod
    def resolve_task(self, name: str) -> str | None:
        """Return the import target for a configured plugin Task."""

    @abstractmethod
    def status(self) -> list[dict]:
        """Return status records for all prepared plugins."""
