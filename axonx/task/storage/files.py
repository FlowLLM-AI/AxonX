"""Atomic filesystem writes shared by runtime and domain modules."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path
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
    """Atomically write text using the project default encoding."""
    atomic_write(path, lambda temporary: temporary.write_text(content, encoding=encoding))


def atomic_write_json(path: Path, value: Any) -> None:
    """Atomically write readable JSON, rejecting NaN and Infinity."""
    content = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
    atomic_write_text(path, content)


def file_revision(path: Path) -> str:
    """Return size and nanosecond mtime; this is not a content checksum."""
    stat = Path(path).stat()
    return f"{stat.st_size}:{stat.st_mtime_ns}"


def snapshot_file(source: Path, target: Path, *, isolated: bool = False) -> None:
    """Link immutable inputs, or copy when isolation or another filesystem requires it."""
    source = Path(source).resolve(strict=True)
    before = source.stat()

    def copy(temporary):
        if isolated:
            shutil.copy2(source, temporary)
        else:
            temporary.unlink()
            try:
                os.link(source, temporary)
            except OSError:
                shutil.copy2(source, temporary)
        after = source.stat()
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ) or file_revision(temporary) != f"{before.st_size}:{before.st_mtime_ns}":
            raise ValueError(f"Source changed during snapshot: {source}")

    atomic_write(target, copy)
