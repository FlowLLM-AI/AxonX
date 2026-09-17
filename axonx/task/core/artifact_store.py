"""Workspace-bound access to task artifacts."""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ...utils.fs import atomic_write, atomic_write_text, file_sha256
from ..base import TaskMetadata, task_type_from_id


class ArtifactStore:
    """Resolve, validate, and persist artifacts in one workspace."""

    def __init__(self, workspace_path: Path) -> None:
        self.workspace_path = workspace_path

    def task_directory(self, task_type: str, task_id: str) -> Path:
        if task_type_from_id(task_id).value != task_type:
            raise ValueError(f"无效的 {task_type} task_id: {task_id}")
        return self.workspace_path / task_type / task_id

    def read_metadata(self, path: Path, *, description: str) -> dict[str, Any]:
        if not path.is_file():
            raise FileNotFoundError(f"{description} metadata 不存在: {path}")
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise TypeError(f"{description} metadata 必须是 JSON 对象")
        return value

    def artifact_path(self, task_dir: Path, metadata: dict[str, Any], name: str) -> Path:
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

    def artifact_record(self, path: Path, root: Path) -> dict[str, Any]:
        try:
            name = str(path.relative_to(root))
        except ValueError:
            name = str(path)
        return {"path": name, "bytes": path.stat().st_size, "sha256": file_sha256(path)}

    def write_metadata(self, path: Path, metadata: TaskMetadata) -> None:
        def json_value(value: Any) -> Any:
            if isinstance(value, float) and not math.isfinite(value):
                return None
            if isinstance(value, dict):
                return {key: json_value(item) for key, item in value.items()}
            if isinstance(value, (list, tuple)):
                return [json_value(item) for item in value]
            return value

        atomic_write_text(
            path,
            json.dumps(json_value(metadata.model_dump(mode="json", by_alias=True)), ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        )

    def atomic_output(self, path: Path, writer: Callable[[Path], object]) -> None:
        atomic_write(path, writer)

    def file_sha256(self, path: Path) -> str:
        return file_sha256(path)
