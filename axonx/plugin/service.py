"""Coordinate plugin preparation and uploaded wheel installation."""

from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import RLock
from typing import Callable

from .builder import build_wheel, source_sha256
from .contributions import index_records
from .inspector import inspect_wheel
from .models import PluginArtifact
from .repository import PluginRepository


class PluginService:
    """Apply plugin changes while keeping persisted contributions consistent."""

    def __init__(
        self,
        repository: PluginRepository,
        installer: Callable[[PluginArtifact], None],
        *,
        auto_install: bool = True,
    ) -> None:
        self.repository = repository
        self.installer = installer
        self.auto_install = auto_install
        self.lock = RLock()

    def load(self) -> None:
        """Load and validate the saved contribution index."""
        self.repository.load()
        index_records(self.repository.records)

    def _check(self, key: str, artifact: PluginArtifact) -> None:
        index_records({**self.repository.records, key: artifact.contributions_dict()})

    def status(self, name: str) -> dict:
        """Return one managed plugin record by distribution or manifest name."""
        with self.lock:
            matches = [
                record
                for record in self.repository.status()
                if name == record.get("distribution") or name in record.get("plugins", ())
            ]
            if not matches:
                raise ValueError(f"Unknown plugin: {name!r}")
            if len(matches) != 1:
                raise ValueError(f"Ambiguous plugin: {name!r}")
            return matches[0]

    def inspect(self, name: str) -> dict:
        """Read the wheel belonging to one managed plugin on this service."""
        with self.lock:
            record = self.status(name)
            wheel = Path(record["wheel"])
            if not wheel.is_file():
                raise FileNotFoundError(f"Plugin wheel not found: {wheel}")
            artifact = inspect_wheel(wheel)
            if artifact.sha256 != record["wheel_sha256"]:
                raise ValueError(f"Plugin wheel SHA-256 mismatch: {wheel}")
            return {
                **record,
                "requirements": artifact.requirements,
            }

    def prepare_source(self, source: Path) -> PluginArtifact:
        """Build a changed source tree and publish its contributions."""
        with self.lock:
            source = source.expanduser().resolve()
            digest = source_sha256(source)
            key = str(source)
            cached = self.repository.get(key)
            cached_wheel = Path(cached.get("wheel", ""))
            if cached.get("source_sha256") == digest and cached_wheel.is_file():
                artifact = inspect_wheel(cached_wheel)
            else:
                artifact = inspect_wheel(
                    build_wheel(source, self.repository.directory / "artifacts" / digest, use_cache=True),
                )
            self._check(key, artifact)
            if self.auto_install and cached.get("wheel_sha256") != artifact.sha256:
                self.installer(artifact)
            self.repository.record(key, artifact, source_hash=digest)
            return artifact

    def install_uploaded_wheel(self, data: bytes, filename: str, sha256: str) -> PluginArtifact:
        """Inspect, install, then publish an uploaded wheel."""
        with self.lock:
            with NamedTemporaryFile(suffix=".whl", delete=False, dir=self.repository.directory) as stream:
                path = Path(stream.name)
                stream.write(data)
            try:
                artifact = inspect_wheel(path)
                if artifact.sha256 != sha256.lower():
                    raise ValueError("Wheel SHA-256 mismatch")
                key = f"remote:{artifact.distribution}"
                if self.repository.get(key).get("wheel_sha256") == artifact.sha256:
                    return artifact
                self._check(key, artifact)
                destination = self.repository.directory / "artifacts" / artifact.sha256 / filename
                destination.parent.mkdir(parents=True, exist_ok=True)
                path.replace(destination)
                artifact = inspect_wheel(destination)
                self.installer(artifact)
                self.repository.record(key, artifact)
                return artifact
            finally:
                path.unlink(missing_ok=True)
