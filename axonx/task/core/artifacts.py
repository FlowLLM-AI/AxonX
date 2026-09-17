"""Shared helpers for task-scoped artifacts."""

from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

from ...utils.fs import atomic_write as atomic_output
from ...utils.fs import atomic_write_text as atomic_text
from ...utils.fs import file_sha256
from ..base import TaskMetadata

__all__ = [
    "artifact_path",
    "artifact_record",
    "atomic_output",
    "atomic_text",
    "file_sha256",
    "normalize_yyyymmdd",
    "read_metadata",
    "task_directory",
    "write_metadata",
]


def task_directory(workspace: Path, task_type: str, task_id: str) -> Path:
    """Return a canonical upstream directory after rejecting path-like IDs."""
    if Path(task_id).name != task_id or "#" not in task_id:
        raise ValueError(f"无效的 {task_type} task_id: {task_id}")
    return workspace / task_type / task_id


def read_metadata(path: Path, *, description: str) -> dict[str, Any]:
    """Read and validate an Artifact metadata JSON object."""
    if not path.is_file():
        raise FileNotFoundError(f"{description} metadata 不存在: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{description} metadata 必须是 JSON 对象")
    return value


def artifact_path(task_dir: Path, metadata: dict[str, Any], name: str) -> Path:
    """Resolve a declared Artifact path without allowing directory escape."""
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


def normalize_yyyymmdd(value: object, *, optional: bool = False) -> str | None:
    """Normalize and validate a compact calendar date."""
    if optional and (value is None or isinstance(value, str) and value.lower() in {"", "none"}):
        return None
    normalized = str(value)
    try:
        parsed = datetime.strptime(normalized, "%Y%m%d")
    except ValueError as exc:
        raise ValueError(f"必须是有效 YYYYMMDD: {normalized}") from exc
    if parsed.strftime("%Y%m%d") != normalized:
        raise ValueError(f"必须是有效 YYYYMMDD: {normalized}")
    return normalized


def artifact_record(path: Path, root: Path) -> dict[str, Any]:
    """Describe an Artifact path, size and content digest."""
    try:
        name = str(path.relative_to(root))
    except ValueError:
        name = str(path)
    return {"path": name, "bytes": path.stat().st_size, "sha256": file_sha256(path)}


def write_metadata(path: Path, metadata: TaskMetadata) -> None:
    """Normalize and atomically persist task Artifact metadata."""

    def json_value(value: Any) -> Any:
        if isinstance(value, float) and not math.isfinite(value):
            return None
        if isinstance(value, dict):
            return {key: json_value(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [json_value(item) for item in value]
        return value

    atomic_text(
        path,
        json.dumps(json_value(metadata.model_dump(mode="json", by_alias=True)), ensure_ascii=False, indent=2, allow_nan=False) + "\n",
    )
