"""Read Task metadata and resolve recorded artifacts safely."""

import json
from collections.abc import Iterable
from pathlib import Path

from .files import file_revision
from ..task_enums import TaskState, TaskType
from ..models.artifacts import (
    ArtifactRecord,
    PredictionProtocol,
    task_protocol,
    validate_protocol,
)


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


def prediction_protocol(
    task_type: TaskType,
    identity: dict[str, str],
    path: Path,
    dates: Iterable,
    score_columns: dict[str, str],
    **payload,
) -> dict:
    return PredictionProtocol(
        **task_protocol(task_type),
        model_identity=identity,
        dates=sorted({str(day) for day in dates}),
        score_columns=score_columns,
        predictions_revision=file_revision(path),
        **payload,
    ).model_dump(mode="json")
