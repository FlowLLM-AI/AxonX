"""Component contract for plugin lifecycle and contribution lookup."""

from abc import ABC, abstractmethod
from pathlib import Path

from ...enumeration import ComponentEnum
from ...plugin.artifact import PluginArtifact
from ...schema import JobConfig
from ..base_component import BaseComponent


class BasePluginComponent(BaseComponent, ABC):
    """Define operations for preparing plugins and exposing contributions."""

    component_type = ComponentEnum.PLUGIN

    @abstractmethod
    def discover(self) -> None:
        """Discover contributions synchronously before the application graph is built."""

    @abstractmethod
    def prepare(self, source: Path) -> PluginArtifact:
        """Prepare a plugin source tree and publish its contributions."""

    @abstractmethod
    def install_wheel(self, data: bytes, expected_sha256: str, filename: str) -> PluginArtifact:
        """Validate and install an uploaded wheel."""

    @abstractmethod
    def job_configs(self) -> dict[str, JobConfig]:
        """Return validated Job configurations contributed by plugins."""

    @abstractmethod
    def status(self) -> list[dict]:
        """Return status records for all prepared plugins."""
