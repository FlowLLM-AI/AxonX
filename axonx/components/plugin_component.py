"""Plugin artifact lifecycle and Task lookup."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import RLock

from ..enumeration import ComponentEnum
from ..plugin.artifact import (
    PluginArtifact,
    build_wheel,
    inspect_wheel,
    install_artifact,
    source_sha256,
)
from .base_component import BaseComponent
from .component_registry import R


@R.register("local")
class PluginComponent(BaseComponent):
    """Build and install configured Task plugins and resolve Task targets."""

    component_type = ComponentEnum.PLUGIN

    def __init__(
        self,
        auto_install=True,
        allow_remote_install=False,
        install_token=None,
        max_wheel_bytes=256 * 1024 * 1024,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.auto_install = auto_install
        self.allow_remote_install = allow_remote_install
        self.install_token = install_token
        self.max_wheel_bytes = max_wheel_bytes
        self.directory = None
        self._tasks: dict[str, str] = {}
        self._task_owners: dict[str, str] = {}
        self._state: dict[str, dict] = {}
        self._install_lock = RLock()

    async def _start(self):
        self.directory = self.workspace_path / "plugins"
        self.directory.mkdir(parents=True, exist_ok=True)
        self._load_state()
        for configured_path in self.app_config.plugins:
            await asyncio.to_thread(self.prepare, Path(configured_path))

    @property
    def state_path(self) -> Path:
        if self.directory is None:
            raise RuntimeError("Plugin component is not started")
        return self.directory / "state.json"

    def _load_state(self):
        if self.state_path.is_file():
            self._state = json.loads(self.state_path.read_text(encoding="utf-8"))
        for key, record in self._state.items():
            for name, target in record.get("tasks", {}).items():
                if name in self._tasks:
                    raise ValueError(f"Task provided by multiple plugins: {name}")
                self._tasks[name] = target
                self._task_owners[name] = key

    def _save_state(self):
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(self._state, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(self.state_path)

    def _install(self, artifact: PluginArtifact):
        install_artifact(artifact)

    def _record(
        self, key: str, artifact: PluginArtifact, *, source_hash: str | None = None
    ):
        for name in tuple(self._tasks):
            if self._task_owners.get(name) == key:
                self._tasks.pop(name)
                self._task_owners.pop(name)
        self._tasks.update(artifact.tasks)
        self._task_owners.update(dict.fromkeys(artifact.tasks, key))
        self._state[key] = {
            "distribution": artifact.distribution,
            "version": artifact.version,
            "plugins": list(artifact.plugin_names),
            "tasks": artifact.tasks,
            "source_sha256": source_hash,
            "wheel_sha256": artifact.sha256,
            "wheel": str(artifact.wheel),
        }
        self._save_state()

    def prepare(self, source: Path) -> PluginArtifact:
        """Build a changed source tree, install it, and publish its Tasks."""
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
                    )
                )
            self._check_tasks(key, artifact)
            if self.auto_install and cached.get("wheel_sha256") != artifact.sha256:
                self._install(artifact)
            self._record(key, artifact, source_hash=digest)
            return artifact

    def install_wheel(
        self, data: bytes, expected_sha256: str, filename: str
    ) -> PluginArtifact:
        """Validate and install one uploaded wheel, then refresh its Task index."""
        if not self.allow_remote_install:
            raise PermissionError("Remote plugin installation is disabled")
        if len(data) > self.max_wheel_bytes:
            raise ValueError("Wheel exceeds configured size limit")
        if Path(filename).name != filename or not filename.endswith(".whl"):
            raise ValueError("Invalid wheel filename")
        with self._install_lock:
            with NamedTemporaryFile(
                suffix=".whl", delete=False, dir=self.directory
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
                self._check_tasks(key, artifact)
                destination = self.directory / "artifacts" / artifact.sha256 / filename
                destination.parent.mkdir(parents=True, exist_ok=True)
                path.replace(destination)
                artifact = inspect_wheel(destination)
                self._install(artifact)
                self._record(key, artifact)
                return artifact
            finally:
                path.unlink(missing_ok=True)

    def resolve_task(self, name: str) -> str | None:
        """Return the import target for a configured plugin Task."""
        return self._tasks.get(name)

    def _check_tasks(self, key: str, artifact: PluginArtifact) -> None:
        duplicate = {
            name
            for name in artifact.tasks
            if name in self._tasks and self._task_owners.get(name) != key
        }
        if duplicate:
            raise ValueError(
                f"Task provided by multiple plugins: {', '.join(sorted(duplicate))}"
            )

    def status(self) -> list[dict]:
        return list(self._state.values())
