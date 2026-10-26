"""Resolve upstream inputs and pin verified artifact bundles and model collections."""

from pathlib import Path

from ..models.artifacts import ArtifactRecord, ModelCollection
from ..models.identity import TaskState
from .artifacts import artifact_record, verify_artifact
from .files import atomic_write_json, file_revision, snapshot_file
from .workspace import load_task_metadata, read_task_metadata, task_id_from_path, task_path


def upstream_task_directory(workspace: Path, task_id: str) -> Path:
    """Resolve an upstream Task, refusing display-only replicas as research inputs."""
    directory = task_path(workspace, task_id)
    metadata = read_task_metadata(directory, task_id)
    if metadata is not None and metadata.replica is not None:
        raise ValueError("Display replicas cannot be used as research inputs")
    return directory


def resolve_input_path(workspace: Path, path: str | Path) -> Path:
    """Resolve an input path and apply the same upstream Task policy to owned paths."""
    candidate = Path(path).expanduser()
    resolved = (candidate if candidate.is_absolute() else workspace / candidate).resolve()
    owner = task_id_from_path(workspace, str(resolved))
    if owner is not None:
        upstream_task_directory(workspace, owner)
    return resolved


def read_upstream_metadata(workspace: Path, task_id: str) -> tuple[Path, dict]:
    """Read one successful upstream record, validating its identity and input policy."""
    root = task_path(workspace, task_id)
    metadata = load_task_metadata(root, task_id)
    if metadata.replica is not None:
        raise ValueError("Display replicas cannot be used as research inputs")
    if metadata.state != TaskState.SUCCEEDED:
        raise ValueError(f"Upstream Task is not successfully completed: {task_id}")
    return root, metadata.model_dump(mode="json")


def upstream_artifact(task, task_id: str, name: str) -> tuple[Path, dict]:
    """Read a successful upstream Task's artifact and verify its published file version."""
    root, metadata = read_upstream_metadata(task.workspace_path, task_id)
    record = ArtifactRecord.model_validate(metadata["output_params"]["artifacts"][name])
    return verify_artifact(root, record), metadata


def pin_upstream_artifacts(task, task_id: str, *names: str, metadata: dict | None = None) -> tuple[Path, ...]:
    """Keep one upstream artifact bundle stable while a fixed Task ID is refreshed."""
    if metadata is None:
        root, metadata = read_upstream_metadata(task.workspace_path, task_id)
    else:
        root = task.upstream_task_dir(task_id)

    def pin(name):
        record = ArtifactRecord.model_validate(metadata["output_params"]["artifacts"][name])
        source = verify_artifact(root, record)
        target = task.task_dir / "inputs" / f"{name}{source.suffix}"
        snapshot_file(source, target, expected_revision=record.revision)
        return target

    return tuple(pin(name) for name in names)


def snapshot_model_collection(manifest_file: Path, destination: Path, *, expected_revision: str | None = None) -> Path:
    """Snapshot and verify every member of a model collection."""
    revision = file_revision(manifest_file)
    content = manifest_file.read_bytes()
    if file_revision(manifest_file) != revision or (expected_revision is not None and revision != expected_revision):
        raise ValueError("Model manifest changed during snapshot")
    collection = ModelCollection.model_validate_json(content)
    records = {}
    for key, member in collection.members.items():
        name = member.model_artifact
        if name in records:
            continue
        record = collection.artifacts[name]
        source = verify_artifact(manifest_file.parent, record)
        target = destination / "members" / key / source.name
        if not target.resolve().is_relative_to(destination.resolve()):
            raise ValueError("Model member path escapes snapshot directory")
        snapshot_file(source, target, expected_revision=record.revision)
        records[name] = artifact_record(target, destination)
    path = destination / "models.json"
    atomic_write_json(path, {**collection.model_dump(mode="json"), "artifacts": records})
    return path
