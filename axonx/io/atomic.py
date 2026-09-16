"""Atomic filesystem writes shared by runtime and domain modules."""

from __future__ import annotations

from collections.abc import Callable
import json
import os
from pathlib import Path
import tempfile
from typing import Any


def atomic_write(path: Path, writer: Callable[[Path], object]) -> None:
    """Write through a temporary sibling and atomically replace *path*."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    os.close(descriptor)
    temporary_path = Path(temporary)
    try:
        writer(temporary_path)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    """Atomically write text using UTF-8 by default."""
    atomic_write(path, lambda temporary: temporary.write_text(content, encoding=encoding))


def atomic_write_json(path: Path, value: Any) -> None:
    """Atomically write readable JSON, rejecting NaN and Infinity."""
    content = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
    atomic_write_text(path, content)
