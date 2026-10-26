"""Read Task metadata and resolve recorded artifacts safely."""

import json
from pathlib import Path

from ..models.artifacts import ArtifactRecord, validate_protocol
from ..models.identity import TaskState
from .files import file_revision


def read_metadata(path: Path) -> dict:
    """Read a successful upstream Task's research output."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"metadata must be a JSON object: {path}")
    validate_protocol(value)
    if value.get("replica") is not None:
        raise ValueError("Display replicas cannot be used as research inputs")
    if value.get("state") != TaskState.SUCCEEDED.value:
        raise ValueError(f"Upstream Task must have succeeded: {path} (state={value.get('state')!r})")
    return value


def artifact_path(task_dir: Path, metadata: dict, name: str) -> Path:
    artifacts = metadata.get("output_params", {}).get("artifacts")
    record = artifacts.get(name) if isinstance(artifacts, dict) else None
    value = record.get("path") if isinstance(record, dict) else None
    if not isinstance(value, str) or not value:
        raise ValueError(f"metadata 缺少 artifacts.{name}.path")
    path = Path(value)
    if path.is_absolute():
        raise ValueError(f"artifacts.{name} 必须是任务目录内的相对路径")
    resolved = (task_dir / path).resolve()
    if not resolved.is_relative_to(task_dir.resolve()):
        raise ValueError(f"artifacts.{name} 不能超出任务目录")
    return resolved


def artifact_record(path: Path, root: Path) -> dict:
    return ArtifactRecord(
        path=path.relative_to(root).as_posix(),
        size=path.stat().st_size,
        revision=file_revision(path),
    ).model_dump()
