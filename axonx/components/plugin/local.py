"""Workspace plugin component and compatibility API."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from ...enums import component_type_name
from ...plugin.artifact import PluginArtifact, install_artifact
from ...plugin.contributions import index_records
from ...plugin.repository import PluginRepository
from ...plugin.service import PluginService
from ...schema import JobConfig
from ...utils.imports import load_symbol
from ..base import BaseComponent
from ..registry import R
from .base import BasePluginComponent


@R.register("local")
class LocalPluginComponent(BasePluginComponent):
    """Expose plugin use cases through the existing component interface."""

    def __init__(
        self,
        auto_install: bool = True,
        allow_remote_install: bool = False,
        install_token: str | None = None,
        max_wheel_bytes: int = 256 * 1024 * 1024,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.auto_install = auto_install
        self.allow_remote_install = allow_remote_install
        self.install_token = install_token
        self.max_wheel_bytes = max_wheel_bytes
        self.directory: Path | None = None
        self._repository: PluginRepository | None = None
        self._service: PluginService | None = None
        self._discovered = False

    def discover(self) -> None:
        """Prepare configured plugins before jobs and routes are built."""
        if self._discovered:
            return
        self.directory = self.workspace_path / "plugins"
        self.directory.mkdir(parents=True, exist_ok=True)
        self._repository = PluginRepository(self.directory)
        self._service = PluginService(self._repository, self._install, auto_install=self.auto_install)
        self._service.load()
        for configured_path in self.app_config.plugins:
            self.prepare(Path(configured_path))
        self._register_components()
        self._discovered = True

    @property
    def state_path(self) -> Path:
        """Return the persistent plugin-state path for the active workspace."""
        if self.directory is None:
            raise RuntimeError("Plugin manager has not discovered its workspace")
        return self.directory / "state.json"

    def _install(self, artifact: PluginArtifact) -> None:
        install_artifact(artifact)

    def _ready(self) -> tuple[PluginRepository, PluginService]:
        if self._repository is None or self._service is None:
            raise RuntimeError("Plugin manager has not discovered its workspace")
        return self._repository, self._service

    def prepare(self, source: Path) -> PluginArtifact:
        """Build a source tree and publish its contributions."""
        _, service = self._ready()
        return service.prepare_source(source)

    def install_wheel(self, data: bytes, expected_sha256: str, filename: str) -> PluginArtifact:
        """Validate and install an uploaded wheel."""
        if not self.allow_remote_install:
            raise PermissionError("Remote plugin installation is disabled")
        if len(data) > self.max_wheel_bytes:
            raise ValueError("Wheel exceeds configured size limit")
        if Path(filename).name != filename or not filename.endswith(".whl"):
            raise ValueError("Invalid wheel filename")
        _, service = self._ready()
        return service.install_uploaded_wheel(data, filename, expected_sha256)

    def job_configs(self) -> dict[str, JobConfig]:
        """Return plugin-contributed Job configurations."""
        repository, _ = self._ready()
        jobs, _, _ = index_records(repository.records)
        return deepcopy(jobs)

    def _register_components(self) -> None:
        repository, _ = self._ready()
        _, components, owners = index_records(repository.records)
        modules = {}
        for component_type, backends in components.items():
            if component_type == "plugin":
                raise ValueError("Plugins cannot contribute plugin component backends")
            for backend, target in backends.items():
                component_class = load_symbol(target, BaseComponent, kind="Component", modules=modules)
                actual_type = component_type_name(component_class.component_type)
                if actual_type != component_type:
                    raise TypeError(
                        f"Component target {target} declares type {actual_type!r}, " f"expected {component_type!r}",
                    )
                self.app_context.registry.add(backend, component_class, owners[(component_type, backend)])

    def status(self) -> list[dict]:
        """Return persisted status records for prepared plugins."""
        repository, _ = self._ready()
        return repository.status()

    def plugin_status(self, name: str) -> dict:
        """Return one managed plugin's saved status."""
        _, service = self._ready()
        return service.status(name)

    def inspect(self, name: str) -> dict:
        """Inspect the managed wheel stored on this service machine."""
        _, service = self._ready()
        return service.inspect(name)
