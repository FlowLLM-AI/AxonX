"""Read-only helpers for browsing the configured workspace."""

# pylint: disable=too-many-return-statements

from __future__ import annotations

import asyncio
import csv
import json
import math
import shutil
from datetime import date, datetime
from decimal import Decimal
from itertools import islice
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
import yaml

from ...components.registry import R
from ..base import BaseStep

TEXT_PREVIEW_BYTES = 512 * 1024
CSV_PREVIEW_ROWS = 200
PARQUET_PREVIEW_ROWS = 5
MAX_DIRECTORY_ENTRIES = 5_000


def _workspace_root(step: BaseStep) -> Path:
    return Path(step.app_config.workspace_dir).expanduser().resolve()


def _resolve_workspace_path(root: Path, relative_path: str) -> Path:
    if not isinstance(relative_path, str):
        raise TypeError("Workspace path must be a string")
    candidate = Path(relative_path)
    if candidate.is_absolute():
        raise ValueError("Workspace path must be relative")
    target = (root / candidate).resolve()
    if not target.is_relative_to(root):
        raise ValueError("Workspace path is outside the configured workspace")
    return target


def _preview_kind(path: Path) -> str | None:
    suffix = path.suffix.lower()
    return {
        ".txt": "text",
        ".md": "markdown",
        ".markdown": "markdown",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".csv": "csv",
        ".parquet": "parquet",
    }.get(suffix)


def _list_entries(root: Path, relative_path: str) -> dict[str, Any]:
    directory = _resolve_workspace_path(root, relative_path)
    if not directory.exists():
        raise ValueError("Workspace directory does not exist")
    if not directory.is_dir():
        raise ValueError("Workspace path is not a directory")

    entries: list[dict[str, Any]] = []
    children = sorted(directory.iterdir(), key=lambda item: item.name.casefold())
    truncated = len(children) > MAX_DIRECTORY_ENTRIES
    for child in children[:MAX_DIRECTORY_ENTRIES]:
        relative = child.relative_to(root).as_posix()
        try:
            stat = child.lstat() if child.is_symlink() else child.stat()
        except (OSError, RuntimeError):
            stat = child.lstat()

        if child.is_symlink():
            kind = "symlink"
        elif child.is_dir():
            kind = "directory"
        else:
            kind = "file"
        preview_kind = _preview_kind(child) if kind == "file" else None
        entries.append(
            {
                "name": child.name,
                "path": relative,
                "kind": kind,
                "preview_kind": preview_kind,
                "supported": preview_kind is not None,
                "size": stat.st_size if kind == "file" else None,
                "modified_at": stat.st_mtime,
            },
        )
    entries.sort(key=lambda entry: (entry["kind"] != "directory", entry["name"].casefold()))
    return {"path": relative_path, "entries": entries, "truncated": truncated}


def _read_text(path: Path) -> tuple[str, bool, int]:
    size = path.stat().st_size
    with path.open("rb") as handle:
        data = handle.read(TEXT_PREVIEW_BYTES + 1)
    truncated = len(data) > TEXT_PREVIEW_BYTES
    if truncated:
        data = data[:TEXT_PREVIEW_BYTES]
    try:
        return data.decode("utf-8-sig"), truncated, size
    except UnicodeDecodeError as exc:
        raise ValueError("File is not valid UTF-8 text") from exc


def _read_complete_text(path: Path) -> tuple[str, int]:
    """Read a structured text file completely so it can be parsed as one value."""
    size = path.stat().st_size
    try:
        return path.read_text(encoding="utf-8-sig"), size
    except UnicodeDecodeError as exc:
        raise ValueError("File is not valid UTF-8 text") from exc


def _json_compatible(value: Any) -> Any:
    """Convert YAML-specific scalar/container values into JSON-safe data."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_compatible(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_compatible(item) for item in value]
    return str(value)


def _preview_parquet(path: Path, full: bool = False) -> dict[str, Any]:
    """Read footer metadata and either a five-row sample or all rows."""
    parquet = pq.ParquetFile(path)
    columns = [field.name for field in parquet.schema_arrow]
    if full:
        records = parquet.read().to_pylist()
    else:
        batch = next(parquet.iter_batches(batch_size=PARQUET_PREVIEW_ROWS), None)
        records = [] if batch is None else batch.to_pylist()
    rows = [[_json_compatible(row.get(column)) for column in columns] for row in records]
    return {
        "kind": "parquet",
        "size": path.stat().st_size,
        "row_count": parquet.metadata.num_rows,
        "row_group_count": parquet.metadata.num_row_groups,
        "columns": columns,
        "schema": [
            {"name": field.name, "type": str(field.type), "nullable": field.nullable} for field in parquet.schema_arrow
        ],
        "rows": rows,
        "preview_limit": PARQUET_PREVIEW_ROWS,
        "full": full,
    }


def _split_frontmatter(content: str) -> tuple[Any, str, str | None]:
    if not content.startswith("---\n") and not content.startswith("---\r\n"):
        return None, content, None
    lines = content.splitlines(keepends=True)
    closing = next((index for index, line in enumerate(lines[1:], 1) if line.strip() == "---"), None)
    if closing is None:
        return None, content, "Frontmatter closing delimiter was not found"
    raw = "".join(lines[1:closing])
    try:
        metadata = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        return None, "".join(lines[closing + 1 :]), f"Invalid frontmatter: {exc}"
    return metadata, "".join(lines[closing + 1 :]), None


def _preview_csv(path: Path, offset: int, limit: int) -> dict[str, Any]:
    size = path.stat().st_size
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            columns = next(reader, [])
            rows = list(islice(reader, offset, offset + limit + 1))
    except UnicodeDecodeError as exc:
        raise ValueError("CSV file is not valid UTF-8 text") from exc
    except csv.Error as exc:
        raise ValueError(f"Invalid CSV file: {exc}") from exc
    return {
        "kind": "csv",
        "size": size,
        "columns": columns,
        "rows": rows[:limit],
        "offset": offset,
        "limit": limit,
        "has_more": len(rows) > limit,
    }


def _preview_file(root: Path, relative_path: str, offset: int, limit: int, full: bool = False) -> dict[str, Any]:
    path = _resolve_workspace_path(root, relative_path)
    if not path.exists():
        raise ValueError("Workspace file does not exist")
    if not path.is_file():
        raise ValueError("Workspace path is not a file")
    kind = _preview_kind(path)
    size = path.stat().st_size
    if kind is None:
        return {"kind": "unsupported", "size": size}
    if kind == "parquet":
        return _preview_parquet(path, full)
    if kind == "csv":
        return _preview_csv(path, offset, limit)

    if kind in {"json", "yaml"}:
        content, size = _read_complete_text(path)
        truncated = False
    else:
        content, truncated, size = _read_text(path)
    if kind == "markdown":
        frontmatter, body, frontmatter_error = _split_frontmatter(content)
        return {
            "kind": kind,
            "size": size,
            "content": body,
            "frontmatter": frontmatter,
            "frontmatter_error": frontmatter_error,
            "truncated": truncated,
        }
    if kind == "json":
        parse_error = None
        data = None
        try:
            data = json.loads(content)
            content = json.dumps(data, ensure_ascii=False, indent=2)
        except json.JSONDecodeError as exc:
            parse_error = f"Line {exc.lineno}, column {exc.colno}: {exc.msg}"
        return {
            "kind": kind,
            "size": size,
            "content": content,
            "data": data,
            "parse_error": parse_error,
            "truncated": False,
        }
    if kind == "yaml":
        parse_error = None
        data = None
        try:
            parsed = yaml.safe_load(content)
            data = _json_compatible(parsed)
            content = yaml.safe_dump(parsed, allow_unicode=True, sort_keys=False)
        except yaml.YAMLError as exc:
            mark = getattr(exc, "problem_mark", None)
            problem = getattr(exc, "problem", None) or str(exc)
            parse_error = f"Line {mark.line + 1}, column {mark.column + 1}: {problem}" if mark is not None else problem
        return {
            "kind": kind,
            "size": size,
            "content": content,
            "data": data,
            "parse_error": parse_error,
            "truncated": False,
        }
    return {"kind": kind, "size": size, "content": content, "truncated": truncated}


def _delete_entry(root: Path, relative_path: str) -> dict[str, str]:
    if not relative_path:
        raise ValueError("The workspace root cannot be deleted")
    candidate = Path(relative_path)
    if candidate.is_absolute():
        raise ValueError("Workspace path must be relative")
    lexical_target = root / candidate
    if lexical_target.is_symlink():
        raise ValueError("Workspace symlinks cannot be deleted")
    target = _resolve_workspace_path(root, relative_path)
    if target == root:
        raise ValueError("The workspace root cannot be deleted")
    if not target.exists():
        raise ValueError("Workspace entry does not exist")
    if target.is_dir():
        shutil.rmtree(target)
        kind = "directory"
    elif target.is_file():
        target.unlink()
        kind = "file"
    else:
        raise ValueError("Workspace entry is not a regular file or directory")
    return {"deleted": relative_path, "kind": kind}


def _delete_entries(root: Path, relative_paths: list[str]) -> dict[str, list[dict[str, str]]]:
    """Validate a batch first, then delete unique top-level selections."""
    if not relative_paths:
        raise ValueError("At least one workspace entry is required")
    if len(relative_paths) > 200:
        raise ValueError("At most 200 workspace entries can be deleted at once")

    normalized: list[str] = []
    for relative_path in dict.fromkeys(relative_paths):
        if not isinstance(relative_path, str) or not relative_path:
            raise ValueError("Workspace paths must be non-empty strings")
        candidate = Path(relative_path)
        if candidate.is_absolute():
            raise ValueError("Workspace path must be relative")
        lexical_target = root / candidate
        if lexical_target.is_symlink():
            raise ValueError("Workspace symlinks cannot be deleted")
        target = _resolve_workspace_path(root, relative_path)
        if target == root:
            raise ValueError("The workspace root cannot be deleted")
        if not target.exists() or not (target.is_file() or target.is_dir()):
            raise ValueError(f"Workspace entry does not exist: {relative_path}")
        normalized.append(target.relative_to(root).as_posix())

    selected = set(normalized)
    roots = [
        path
        for path in normalized
        if not any(parent.as_posix() in selected for parent in Path(path).parents if parent.as_posix() != ".")
    ]
    deleted = [_delete_entry(root, path) for path in roots]
    return {"deleted": deleted}


@R.register("list_workspace_entries_step")
class ListWorkspaceEntriesStep(BaseStep):
    """List one directory without walking the complete workspace tree."""

    async def execute(self):
        relative_path = self.context.get("path", "")
        self.response.answer = await asyncio.to_thread(_list_entries, _workspace_root(self), relative_path)


@R.register("preview_workspace_file_step")
class PreviewWorkspaceFileStep(BaseStep):
    """Return a bounded preview for one supported workspace file."""

    async def execute(self):
        relative_path = self.context["path"]
        offset = self.context.get("offset", 0)
        limit = min(self.context.get("limit", CSV_PREVIEW_ROWS), CSV_PREVIEW_ROWS)
        full = self.context.get("full", False)
        self.response.answer = await asyncio.to_thread(
            _preview_file,
            _workspace_root(self),
            relative_path,
            offset,
            limit,
            full,
        )


@R.register("delete_workspace_entry_step")
class DeleteWorkspaceEntryStep(BaseStep):
    """Delete one file or directory after workspace-boundary validation."""

    async def execute(self):
        self.response.answer = await asyncio.to_thread(_delete_entry, _workspace_root(self), self.context["path"])


@R.register("delete_workspace_entries_step")
class DeleteWorkspaceEntriesStep(BaseStep):
    """Delete multiple validated workspace entries in one request."""

    async def execute(self):
        self.response.answer = await asyncio.to_thread(
            _delete_entries,
            _workspace_root(self),
            self.context["paths"],
        )
