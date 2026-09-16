"""Preview supported workspace files."""

import csv
import json
import math
from datetime import date, datetime
from decimal import Decimal
from itertools import islice
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
import yaml

from .paths import resolve_workspace_path as _resolve_workspace_path

TEXT_PREVIEW_BYTES = 512 * 1024
CSV_PREVIEW_ROWS = 200
PARQUET_PREVIEW_ROWS = 5


def preview_kind(path: Path) -> str | None:
    return {
        ".txt": "text",
        ".md": "markdown",
        ".markdown": "markdown",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".csv": "csv",
        ".parquet": "parquet",
    }.get(path.suffix.lower())


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
    closing = next(
        (index for index, line in enumerate(lines[1:], 1) if line.strip() == "---"),
        None,
    )
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


def preview_file(root: Path, relative_path: str, offset: int, limit: int, full: bool = False) -> dict[str, Any]:
    path = _resolve_workspace_path(root, relative_path)
    if not path.exists():
        raise ValueError("Workspace file does not exist")
    if not path.is_file():
        raise ValueError("Workspace path is not a file")
    kind = preview_kind(path)
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
