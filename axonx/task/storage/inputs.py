"""Resolve upstream artifacts directly and validate the executions that produced them."""

from pathlib import Path

from ..models.artifacts import ArtifactRecord
from ..models.identity import TaskState
from ..models.lifecycle import InputSource
from .artifacts import verify_artifact
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
    _, metadata = read_upstream_metadata(task.workspace_path, task_id)
    (path,) = upstream_artifacts(task, task_id, name, metadata=metadata)
    return path, metadata


def upstream_artifacts(task, task_id: str, *names: str, metadata: dict | None = None) -> tuple[Path, ...]:
    """Read verified upstream files in place and record their execution and revisions."""
    if metadata is None:
        root, metadata = read_upstream_metadata(task.workspace_path, task_id)
    else:
        root = task.upstream_task_dir(task_id)

    records = {}

    def resolve(name):
        record = ArtifactRecord.model_validate(metadata["output_params"]["artifacts"][name])
        source = verify_artifact(root, record)
        records[name] = record
        return source

    paths = tuple(resolve(name) for name in names)
    record_input_source(task, task_id, metadata["started_at"], records)
    return paths


def record_input_source(task, task_id: str, started_at, artifacts: dict) -> None:
    """Pin one producer execution and its consumed files, including completed live windows."""
    current = getattr(task, "_metadata", None)
    if current is not None and current.state == TaskState.RUNNING and current.task_id != task_id:
        reference = InputSource(started_at=started_at, artifacts=artifacts)
        previous = current.input_sources.get(task_id)
        if previous is not None:
            if previous.started_at != reference.started_at or any(
                key in previous.artifacts and previous.artifacts[key] != record
                for key, record in reference.artifacts.items()
            ):
                raise ValueError(f"Upstream input changed during execution: {task_id}")
            reference.artifacts = previous.artifacts | reference.artifacts
        current.input_sources[task_id] = reference


def upstream_input_artifact(task, metadata: dict, task_id: str, name: str) -> Path:
    """Read a producer's input at the execution and revision that producer consumed."""
    reference = InputSource.model_validate(metadata["input_sources"][task_id])
    _, current = read_upstream_metadata(task.workspace_path, task_id)
    if reference.started_at.isoformat() != InputSource(started_at=current["started_at"]).started_at.isoformat():
        raise ValueError(f"Upstream execution changed: {task_id}")
    record = ArtifactRecord.model_validate(current["output_params"]["artifacts"][name])
    if record != reference.artifacts[name]:
        raise ValueError(f"Upstream input changed: {task_id}/{name}")
    return upstream_artifacts(task, task_id, name, metadata=current)[0]


def verify_input_sources(task) -> None:
    """Reject replaced upstream executions or files before reporting success."""
    for task_id, source in task.metadata.input_sources.items():
        root = upstream_task_directory(task.workspace_path, task_id)
        metadata = load_task_metadata(root, task_id)
        if metadata.started_at != source.started_at:
            raise ValueError(f"Upstream execution changed during execution: {task_id}")
        if metadata.state != TaskState.SUCCEEDED:
            published = {
                f"{window['key']}/{name}": record
                for window in metadata.output_params.get("windows", [])
                if window.get("status") == "done"
                for name, record in window.get("artifacts", {}).items()
            }
            if any(published.get(name) != record.model_dump(mode="json") for name, record in source.artifacts.items()):
                raise ValueError(f"Upstream inputs are no longer published: {task_id}")
        for record in source.artifacts.values():
            verify_artifact(root, record)
