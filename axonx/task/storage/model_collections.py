"""Domain execution and shared operations."""

from __future__ import annotations

from pathlib import Path

from ...common.fs.atomic import atomic_write_json
from ...common.fs.revision import file_revision
from ...common.fs.snapshot import snapshot_file
from ..models.artifacts import ModelCollection
from .artifacts import artifact_record


def snapshot_model_collection(manifest_file: Path, destination: Path, *, expected_revision: str | None = None) -> Path:
    revision = file_revision(manifest_file)
    content = manifest_file.read_bytes()
    if file_revision(manifest_file) != revision or (expected_revision is not None and revision != expected_revision):
        raise ValueError("Model manifest changed during snapshot")
    manifest = ModelCollection.model_validate_json(content).model_dump(mode="json")
    records = {}
    for key, member in manifest["members"].items():
        name = member["model_artifact"]
        source = manifest_file.parent / manifest["artifacts"][name]["path"]
        target = destination / "members" / key / source.name
        if not target.resolve().is_relative_to(destination.resolve()):
            raise ValueError("Model member path escapes snapshot directory")
        snapshot_file(source, target)
        if file_revision(target) != manifest["artifacts"][name]["revision"]:
            raise ValueError("Model collection changed during snapshot")
        records[name] = artifact_record(target, destination)
    path = destination / "models.json"
    atomic_write_json(path, {**manifest, "artifacts": records})
    return path
