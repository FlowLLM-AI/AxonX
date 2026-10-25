"""Published task artifact references and immutable business-file snapshots."""

from pathlib import Path

from ...common.fs.revision import file_revision
from ...common.fs.snapshot import snapshot_file
from ..task_enums import TaskState
from .artifacts import artifact_path, artifact_record
from .model_collections import snapshot_model_collection
from .workspace import read_task_metadata


def artifacts(root: Path, **paths: Path | None) -> dict:
    return {name: artifact_record(path, root) for name, path in paths.items() if path is not None}


def publish_artifacts(task, **paths: Path | None) -> dict:
    published = {}
    for name, path in paths.items():
        if path is None:
            continue
        path = Path(path)
        if path.resolve().is_relative_to(task.task_dir.resolve()):
            published[name] = artifact_record(path, task.task_dir)
            continue
        target = task.task_dir / "artifacts" / f"{name}{path.suffix}"

        snapshot_file(path, target)
        published[name] = artifact_record(target, task.task_dir)
    return published


def _source_metadata(task, task_id: str):
    root = task.source_task_dir(task_id)
    metadata = read_task_metadata(root, task_id)
    if metadata is None or metadata.state != TaskState.SUCCEEDED:
        raise ValueError(f"Source Task is not successfully completed: {task_id}")
    return root, metadata.model_dump(mode="json")


def source_artifact(task, task_id: str, name: str, *, registration: str | None = None):
    root, metadata = _source_metadata(task, task_id)
    if registration is not None and metadata["reg_name"] != registration:
        raise ValueError(f"Expected {registration} source")
    path = artifact_path(root, metadata, name)
    if not path.is_file():
        raise FileNotFoundError(path)
    expected = metadata["output_params"]["artifacts"][name]["revision"]
    if file_revision(path) != expected:
        raise ValueError(f"Artifact revision mismatch: {path}")
    return path, metadata


def pin_source_artifacts(task, task_id: str, *names: str, metadata: dict | None = None) -> tuple[Path, ...]:
    """Keep one upstream artifact bundle stable while a fixed Task ID is refreshed."""
    if metadata is None:
        root, metadata = _source_metadata(task, task_id)
    else:
        root = task.source_task_dir(task_id)

    def pin(name):
        source = artifact_path(root, metadata, name)
        target = task.task_dir / "inputs" / f"{name}{source.suffix}"

        snapshot_file(source, target)
        expected = metadata["output_params"]["artifacts"][name]["revision"]
        if file_revision(target) != expected:
            raise ValueError("Source Task refreshed during input snapshot; retry the completed run")
        return target

    return tuple(pin(name) for name in names)


def pin_models(task, source_id=None, manifest_file=None):
    """Snapshot and verify every member of a model collection."""
    expected = None
    if source_id:
        manifest_file, metadata = source_artifact(task, source_id, "model_manifest")
        expected = metadata["output_params"]["artifacts"]["model_manifest"]["revision"]
    else:
        manifest_file = task.resolve_workspace_path(manifest_file)
    return snapshot_model_collection(
        Path(manifest_file),
        task.task_dir / "model_snapshot",
        expected_revision=expected,
    )
