"""Component contract for plugin lifecycle and contribution lookup."""

from abc import ABC, abstractmethod
from pathlib import Path

from ...enums import ComponentEnum
from ...schema import JobConfig, PluginArtifact
from ..base import BaseComponent


class BasePluginComponent(BaseComponent, ABC):
    """Define operations for preparing plugins and exposing contributions."""

    component_type = ComponentEnum.PLUGIN
    allow_remote_install: bool
    install_token: str | None
    max_wheel_bytes: int

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

    @abstractmethod
    def plugin_status(self, name: str) -> dict:
        """Return one managed plugin's saved status."""

    @abstractmethod
    def inspect(self, name: str) -> dict:
        """Inspect one managed plugin's wheel on the service machine."""
