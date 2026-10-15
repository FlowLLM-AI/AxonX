"""Read Task metadata and resolve recorded artifacts safely."""

import json
from collections.abc import Iterable
from pathlib import Path

from ...constants import AXONX_DEFAULT_ENCODING
from ...enums import TaskState, TaskType
from ...utils.fs import file_sha256
from ..schemas.protocol import task_protocol, validate_protocol
from ..schemas.prediction import PredictionProtocol
from ..schemas.artifact import ArtifactRecord


def read_metadata(path: Path) -> dict:
    """Read a successful upstream Task's research output."""
    value = json.loads(path.read_text(encoding=AXONX_DEFAULT_ENCODING))
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
        sha256=file_sha256(path),
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
        predictions_sha256=file_sha256(path),
        **payload,
    ).model_dump(mode="json")
