"""Read Task metadata and resolve recorded artifacts safely."""

import json
from pathlib import Path

from ...constants import AXONX_DEFAULT_ENCODING
from ...utils.fs import file_sha256


def read_metadata(path: Path) -> dict:
    value = json.loads(path.read_text(encoding=AXONX_DEFAULT_ENCODING))
    if not isinstance(value, dict):
        raise TypeError(f"metadata must be a JSON object: {path}")
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
    return {
        "path": str(path.relative_to(root)),
        "size": path.stat().st_size,
        "sha256": file_sha256(path),
    }
