"""Bounded renderers for supported workspace file formats."""

import codecs
import csv
import json
import math
from datetime import date, datetime
from itertools import islice
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
import yaml

from .models import (
    CsvPreview,
    FilePreview,
    MarkdownPreview,
    JsonlPreview,
    JsonlRow,
    ParquetColumn,
    ParquetPreview,
    StructuredPreview,
    TextPreview,
    UnsupportedPreview,
)
from ...common.fs.paths import ConfinedPaths

PREVIEW_ROWS = 200
MAX_PREVIEW_ROWS = 5_000
TEXT_PREVIEW_BYTES = 512 * 1024
MAX_STRUCTURED_BYTES = 32 * 1024 * 1024
PREVIEW_KINDS = {
    ".txt": "text",
    ".md": "markdown",
    ".markdown": "markdown",
    ".json": "json",
    ".jsonl": "jsonl",
    ".ndjson": "jsonl",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".csv": "csv",
    ".parquet": "parquet",
}


def preview_kind(path: Path) -> str | None:
    return PREVIEW_KINDS.get(path.suffix.lower())


def preview_workspace_file(
    workspace_path: Path,
    relative_path: str,
    offset: int = 0,
    limit: int = PREVIEW_ROWS,
    *,
    max_bytes: int | None = None,
) -> FilePreview:
    if isinstance(offset, bool) or not isinstance(offset, int):
        raise TypeError("Preview offset must be an integer")
    if offset < 0:
        raise ValueError("Preview offset must be non-negative")
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise TypeError("Preview limit must be an integer")
    if limit < 1 or limit > MAX_PREVIEW_ROWS:
        raise ValueError(f"Preview limit must be between 1 and {MAX_PREVIEW_ROWS}")
    if max_bytes is not None and (
        isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or not 1 <= max_bytes <= MAX_STRUCTURED_BYTES
    ):
        raise ValueError(f"max_bytes must be an integer between 1 and {MAX_STRUCTURED_BYTES}")
    path = ConfinedPaths(workspace_path).resolve_file(relative_path)
    size = path.stat().st_size
    kind = preview_kind(path)
    if kind is None:
        return UnsupportedPreview(size=size)
    if kind == "parquet":
        return _preview_parquet(path, size, offset, limit)
    if kind == "jsonl":
        return _preview_jsonl(path, size, offset, limit)
    if kind == "csv":
        return _preview_csv(path, size, offset, limit)
    if kind in {"json", "yaml"}:
        return _preview_structured(path, size, kind, max_bytes=max_bytes)
    return _preview_text(path, size, kind, max_bytes=max_bytes or TEXT_PREVIEW_BYTES)


def _json_compatible(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_compatible(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_compatible(item) for item in value]
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _read_text_prefix(path: Path, max_bytes: int) -> tuple[str, bool]:
    with path.open("rb") as handle:
        data = handle.read(max_bytes + 1)
    truncated = len(data) > max_bytes
    try:
        # Buffer only an incomplete trailing code point; reject invalid bytes inside the prefix.
        content = (
            codecs.getincrementaldecoder("utf-8-sig")().decode(data[:max_bytes], final=False)
            if truncated
            else data.decode("utf-8-sig")
        )
    except UnicodeDecodeError as exc:
        raise ValueError("File is not valid UTF-8 text") from exc
    return content, truncated


def _preview_text(path: Path, size: int, kind: str, *, max_bytes: int = TEXT_PREVIEW_BYTES) -> FilePreview:
    content, truncated = _read_text_prefix(path, max_bytes)
    if kind == "text":
        return TextPreview(size=size, content=content, truncated=truncated)
    frontmatter, body, frontmatter_error = _split_frontmatter(content)
    return MarkdownPreview(
        size=size,
        content=body,
        frontmatter=frontmatter,
        frontmatter_error=frontmatter_error,
        truncated=truncated,
    )


def _split_frontmatter(content: str) -> tuple[Any, str, str | None]:
    if not content.startswith(("---\n", "---\r\n")):
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
        metadata = _json_compatible(yaml.safe_load(raw))
    except yaml.YAMLError as exc:
        return None, "".join(lines[closing + 1 :]), f"Invalid frontmatter: {exc}"
    return metadata, "".join(lines[closing + 1 :]), None


def _preview_structured(path: Path, size: int, kind: str, *, max_bytes: int | None = None) -> StructuredPreview:
    if max_bytes is None and size > MAX_STRUCTURED_BYTES:
        return StructuredPreview(
            kind=kind,
            size=size,
            truncated=True,
            parse_error=f"File exceeds the {MAX_STRUCTURED_BYTES} byte preview limit",
        )
    content, truncated = _read_text_prefix(path, max_bytes or MAX_STRUCTURED_BYTES)
    if truncated:
        return StructuredPreview(
            kind=kind,
            size=size,
            content=content,
            truncated=True,
            parse_error="Partial preview; increase max_bytes to parse the complete file",
        )
    return _preview_json(content, size) if kind == "json" else _preview_yaml(content, size)


def _preview_json(content: str, size: int) -> StructuredPreview:
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        return StructuredPreview(
            kind="json",
            size=size,
            content=content,
            parse_error=f"Line {exc.lineno}, column {exc.colno}: {exc.msg}",
        )
    return StructuredPreview(
        kind="json",
        size=size,
        data=data,
    )


def _preview_yaml(content: str, size: int) -> StructuredPreview:
    try:
        parsed = yaml.safe_load(content)
        return StructuredPreview(
            kind="yaml",
            size=size,
            data=_json_compatible(parsed),
        )
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        problem = getattr(exc, "problem", None) or str(exc)
        error = f"Line {mark.line + 1}, column {mark.column + 1}: {problem}" if mark is not None else problem
        return StructuredPreview(kind="yaml", size=size, content=content, parse_error=error)


def _read_jsonl_line(handle, budget: int) -> tuple[bytes, bool]:
    """Bound memory even when a single record exceeds the page byte budget."""
    raw = handle.readline(budget + 1)
    oversized = len(raw) > budget
    if oversized and not raw.endswith(b"\n"):
        while chunk := handle.readline(TEXT_PREVIEW_BYTES):
            if chunk.endswith(b"\n"):
                break
    return raw[:budget], oversized


def _preview_jsonl(path: Path, size: int, offset: int, limit: int) -> JsonlPreview:
    rows = []
    remaining = TEXT_PREVIEW_BYTES
    truncated = False
    with path.open("rb") as handle:
        for _ in range(offset):
            raw, _ = _read_jsonl_line(handle, TEXT_PREVIEW_BYTES)
            if not raw:
                break
        for index in range(limit):
            if remaining <= 0:
                break
            raw, oversized = _read_jsonl_line(handle, remaining)
            if not raw:
                break
            remaining -= len(raw)
            content = raw.decode("utf-8-sig" if offset + index == 0 else "utf-8", errors="replace").rstrip("\r\n")
            data = None
            error = None
            if oversized:
                truncated = True
            else:
                try:
                    # Strict UTF-8 validation belongs to the individual row.
                    content = raw.decode("utf-8-sig" if offset + index == 0 else "utf-8").rstrip("\r\n")
                    data = _json_compatible(json.loads(content))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    error = str(exc)
            rows.append(
                JsonlRow(line=offset + index + 1, content=content, data=data, parse_error=error, truncated=oversized)
            )
        has_more = bool(handle.read(1))
    return JsonlPreview(size=size, rows=rows, offset=offset, limit=limit, has_more=has_more, truncated=truncated)


def _preview_csv(path: Path, size: int, offset: int, limit: int) -> CsvPreview:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            columns = next(reader, [])
            rows = list(islice(reader, offset, offset + limit + 1))
    except UnicodeDecodeError as exc:
        raise ValueError("CSV file is not valid UTF-8 text") from exc
    except csv.Error as exc:
        raise ValueError(f"Invalid CSV file: {exc}") from exc
    return CsvPreview(
        size=size,
        columns=columns,
        rows=rows[:limit],
        offset=offset,
        limit=limit,
        has_more=len(rows) > limit,
    )


def _preview_parquet(path: Path, size: int, offset: int, limit: int) -> ParquetPreview:
    parquet = pq.ParquetFile(path)
    fields = parquet.schema_arrow
    columns = [field.name for field in fields]
    records: list[dict[str, Any]] = []
    skipped = 0
    for batch in parquet.iter_batches(batch_size=limit):
        if skipped + batch.num_rows <= offset:
            skipped += batch.num_rows
            continue
        start = max(0, offset - skipped)
        needed = limit - len(records)
        records.extend(batch.slice(start, needed).to_pylist())
        skipped += batch.num_rows
        if len(records) >= limit:
            break
    row_count = parquet.metadata.num_rows
    return ParquetPreview(
        size=size,
        row_count=row_count,
        row_group_count=parquet.metadata.num_row_groups,
        columns=columns,
        column_schema=[
            ParquetColumn(name=field.name, type=str(field.type), nullable=field.nullable) for field in fields
        ],
        rows=[[_json_compatible(row.get(column)) for column in columns] for row in records],
        offset=offset,
        limit=limit,
        has_more=offset + len(records) < row_count,
    )
