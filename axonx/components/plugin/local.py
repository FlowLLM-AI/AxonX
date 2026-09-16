"""Plugin artifact lifecycle and contribution lookup."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import RLock

from ...plugin.artifact import (
    PluginArtifact,
    build_wheel,
    inspect_wheel,
    install_artifact,
    source_sha256,
)
from ...utils.fs import atomic_write_json
from ...schema import JobConfig
from ...enums import component_type_name
from ...utils.imports import load_symbol
from ..base import BaseComponent
from ..registry import R
from .base import BasePluginComponent


@R.register("local")
class LocalPluginComponent(BasePluginComponent):
    """Build and install configured plugins and expose their contributions."""

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
        self.directory = None
        self._components: dict[str, dict[str, str]] = {}
        self._component_owners: dict[tuple[str, str], str] = {}
        self._jobs: dict[str, JobConfig] = {}
        self._state: dict[str, dict] = {}
        self._install_lock = RLock()
        self._discovered = False

    def discover(self) -> None:
        """Prepare configured plugins before jobs and service routes are built."""
        if self._discovered:
            return
        self.directory = self.workspace_path / "plugins"
        self.directory.mkdir(parents=True, exist_ok=True)
        self._load_state()
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

    def _load_state(self):
        if self.state_path.is_file():
            self._state = json.loads(self.state_path.read_text(encoding="utf-8"))
        self._rebuild_index()

    def _save_state(self):
        atomic_write_json(self.state_path, self._state)

    def _install(self, artifact: PluginArtifact):
        install_artifact(artifact)

    def _record(
        self,
        key: str,
        artifact: PluginArtifact,
        *,
        source_hash: str | None = None,
    ):
        self._state[key] = {
            "distribution": artifact.distribution,
            "version": artifact.version,
            "plugins": list(artifact.plugin_names),
            **artifact.contributions_dict(),
            "source_sha256": source_hash,
            "wheel_sha256": artifact.sha256,
            "wheel": str(artifact.wheel),
        }
        self._rebuild_index()
        self._save_state()

    def prepare(self, source: Path) -> PluginArtifact:
        """Build a changed source tree, install it, and publish its contributions."""
        with self._install_lock:
            source = source.expanduser().resolve()
            digest = source_sha256(source)
            key = str(source)
            cached = self._state.get(key, {})
            cached_wheel = Path(cached.get("wheel", ""))
            if cached.get("source_sha256") == digest and cached_wheel.is_file():
                artifact = inspect_wheel(cached_wheel)
            else:
                artifact = inspect_wheel(
                    build_wheel(
                        source,
                        self.directory / "artifacts" / digest,
                        use_cache=True,
                    ),
                )
            self._check_contributions(key, artifact)
            if self.auto_install and cached.get("wheel_sha256") != artifact.sha256:
                self._install(artifact)
            self._record(key, artifact, source_hash=digest)
            return artifact

    def install_wheel(
        self,
        data: bytes,
        expected_sha256: str,
        filename: str,
    ) -> PluginArtifact:
        """Install one uploaded wheel and persist its contributions.

        Tasks become discoverable immediately. Jobs are picked up the next time
        the application graph is built.
        """
        if not self.allow_remote_install:
            raise PermissionError("Remote plugin installation is disabled")
        if len(data) > self.max_wheel_bytes:
            raise ValueError("Wheel exceeds configured size limit")
        if Path(filename).name != filename or not filename.endswith(".whl"):
            raise ValueError("Invalid wheel filename")
        with self._install_lock:
            with NamedTemporaryFile(
                suffix=".whl",
                delete=False,
                dir=self.directory,
            ) as stream:
                path = Path(stream.name)
                stream.write(data)
            try:
                artifact = inspect_wheel(path)
                if artifact.sha256 != expected_sha256.lower():
                    raise ValueError("Wheel SHA-256 mismatch")
                key = f"remote:{artifact.distribution}"
                if self._state.get(key, {}).get("wheel_sha256") == artifact.sha256:
                    return artifact
                self._check_contributions(key, artifact)
                destination = self.directory / "artifacts" / artifact.sha256 / filename
                destination.parent.mkdir(parents=True, exist_ok=True)
                path.replace(destination)
                artifact = inspect_wheel(destination)
                self._install(artifact)
                self._record(key, artifact)
                return artifact
            finally:
                path.unlink(missing_ok=True)

    def job_configs(self) -> dict[str, JobConfig]:
        """Return a copy of all plugin-contributed Job configurations."""
        return deepcopy(self._jobs)

    def _check_contributions(self, key: str, artifact: PluginArtifact) -> None:
        candidate = {
            **self._state,
            key: artifact.contributions_dict(),
        }
        self._index_records(candidate)

    def _rebuild_index(self) -> None:
        self._jobs, self._components, self._component_owners = self._index_records(self._state)

    @staticmethod
    def _index_records(
        records: dict[str, dict],
    ) -> tuple[dict[str, JobConfig], dict[str, dict[str, str]], dict[tuple[str, str], str]]:
        jobs: dict[str, JobConfig] = {}
        components: dict[str, dict[str, str]] = {}
        component_owners: dict[tuple[str, str], str] = {}
        task_owners: dict[str, str] = {}
        job_owners: dict[str, str] = {}

        for owner, record in records.items():
            for name in record.get("tasks", {}):
                if name in task_owners:
                    previous = task_owners[name]
                    raise ValueError(f"Task {name!r} is provided by plugins {previous!r} and {owner!r}")
                task_owners[name] = owner
            for name, raw_config in record.get("jobs", {}).items():
                if name in job_owners:
                    previous = job_owners[name]
                    raise ValueError(f"Job {name!r} is provided by plugins {previous!r} and {owner!r}")
                jobs[name] = JobConfig.model_validate(raw_config)
                job_owners[name] = owner
            for component_type, backends in record.get("components", {}).items():
                registered = components.setdefault(component_type, {})
                for backend, target in backends.items():
                    identity = (component_type, backend)
                    if identity in component_owners:
                        previous = component_owners[identity]
                        raise ValueError(
                            f"Component backend {component_type}:{backend} is provided by "
                            f"plugins {previous!r} and {owner!r}",
                        )
                    registered[backend] = target
                    component_owners[identity] = owner
        return jobs, components, component_owners

    def _register_components(self) -> None:
        modules = {}
        for component_type, backends in self._components.items():
            if component_type == "plugin":
                raise ValueError("Plugins cannot contribute plugin component backends")
            for backend, target in backends.items():
                component_class = load_symbol(target, BaseComponent, kind="Component", modules=modules)
                actual_type = component_type_name(component_class.component_type)
                if actual_type != component_type:
                    raise TypeError(
                        f"Component target {target} declares type {actual_type!r}, " f"expected {component_type!r}",
                    )
                owner = self._component_owners[(component_type, backend)]
                self.app_context.registry.add(backend, component_class, owner)

    def status(self) -> list[dict]:
        """Return persisted status records for all prepared plugins."""
        return deepcopy(list(self._state.values()))
