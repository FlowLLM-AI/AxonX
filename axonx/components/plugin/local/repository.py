"""Workspace-scoped plugin state persistence."""

from copy import deepcopy
import json
from pathlib import Path

from ....plugin.models import PluginArtifact
from ....utils.fs import atomic_write_json


class PluginRepository:
    """Read and write installed plugin records without exposing mutable state."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.path = directory / "state.json"
        self.records: dict[str, dict] = {}

    def load(self) -> None:
        """Load the current workspace state."""
        self.records = json.loads(self.path.read_text(encoding="utf-8")) if self.path.is_file() else {}

    def get(self, key: str) -> dict:
        """Return one independent record snapshot."""
        return deepcopy(self.records.get(key, {}))

    def status(self) -> list[dict]:
        """Return independent snapshots for the status API."""
        return deepcopy(list(self.records.values()))

    def record(self, key: str, artifact: PluginArtifact, *, source_hash: str | None = None) -> None:
        """Persist metadata only after inspection and installation succeed."""
        entry = {
            "distribution": artifact.distribution,
            "version": artifact.version,
            "plugins": list(artifact.plugin_names),
            **artifact.contributions_dict(),
            "source_sha256": source_hash,
            "wheel_sha256": artifact.sha256,
            "wheel": str(artifact.wheel),
        }
        candidate = {**self.records, key: entry}
        atomic_write_json(self.path, candidate)
        self.records = candidate
