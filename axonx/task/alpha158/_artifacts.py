"""Small, shared helpers for task-scoped Alpha158 artifacts."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def task_directory(workspace: Path, task_type: str, task_id: str) -> Path:
    """Return a canonical upstream directory after rejecting path-like IDs."""
    if Path(task_id).name != task_id or not task_id.startswith(f"{task_type}#"):
        raise ValueError(f"无效的 {task_type} task_id: {task_id}")
    return workspace / task_type / task_id


def read_metadata(path: Path, *, description: str) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"{description} metadata 不存在: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{description} metadata 必须是 JSON 对象")
    return value


def artifact_path(task_dir: Path, metadata: dict[str, Any], name: str) -> Path:
    artifacts = metadata.get("artifacts")
    value = artifacts.get(name) if isinstance(artifacts, dict) else None
    if not isinstance(value, str) or not value:
        raise ValueError(f"metadata 缺少 artifacts.{name}")
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


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_record(path: Path, root: Path) -> dict[str, Any]:
    try:
        name = str(path.relative_to(root))
    except ValueError:
        name = str(path)
    return {"path": name, "bytes": path.stat().st_size, "sha256": file_sha256(path)}


def metadata_header(*, task_name: str, task_id: str, task_type: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "task_name": task_name,
        "task_id": task_id,
        "task_type": task_type,
        "created_at": datetime.now(UTC).isoformat(),
    }


def atomic_output(path: Path, writer: Callable[[Path], object]) -> None:
    """Write one artifact through a temporary sibling and atomically replace it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp", text=True)
    os.close(descriptor)
    temporary_path = Path(temporary)
    try:
        writer(temporary_path)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def atomic_text(path: Path, content: str) -> None:
    atomic_output(path, lambda temporary: temporary.write_text(content, encoding="utf-8"))


def write_metadata(path: Path, metadata: dict[str, Any]) -> None:
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
        json.dumps(json_value(metadata), ensure_ascii=False, indent=2, allow_nan=False) + "\n",
    )
