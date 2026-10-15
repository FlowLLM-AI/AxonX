"""Portable, verified snapshots of model collections."""

import hashlib
from pathlib import Path

from ...utils.fs import atomic_write_json, file_sha256, snapshot_file
from ..protocol import ModelCollection
from .artifacts import artifact_record


def snapshot_model_collection(manifest_file: Path, destination: Path, *, expected_sha256: str | None = None) -> Path:
    content = manifest_file.read_bytes()
    if expected_sha256 is not None and hashlib.sha256(content).hexdigest() != expected_sha256:
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
        if file_sha256(target) != manifest["artifacts"][name]["sha256"]:
            raise ValueError("Model collection changed during snapshot")
        records[name] = artifact_record(target, destination)
    path = destination / "models.json"
    atomic_write_json(path, {**manifest, "artifacts": records})
    return path
