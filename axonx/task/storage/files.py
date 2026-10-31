"""Atomic writes, verified output copies and exclusive publication leases."""

from __future__ import annotations

import fcntl
import json
import os
import shutil
import tempfile
from collections.abc import Callable
from contextlib import contextmanager
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


def atomic_write_json(path: Path, value: Any) -> None:
    """Atomically write readable JSON, rejecting NaN and Infinity."""
    content = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
    atomic_write(path, lambda temporary: temporary.write_text(content, encoding="utf-8"))


def file_revision(path: Path) -> str:
    """Return size and nanosecond mtime; this is not a content checksum."""
    stat = Path(path).stat()
    return f"{stat.st_size}:{stat.st_mtime_ns}"


def copy_file(
    source: Path,
    target: Path,
    *,
    expected_revision: str | None = None,
) -> None:
    """Copy a published output atomically and reject concurrent source changes."""
    source = Path(source).resolve(strict=True)
    before = source.stat()
    revision = f"{before.st_size}:{before.st_mtime_ns}"
    if expected_revision is not None and revision != expected_revision:
        raise ValueError(f"Source revision mismatch: {source}")

    def copy(temporary):
        shutil.copy2(source, temporary)
        after = source.stat()
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ) or file_revision(temporary) != revision:
            raise ValueError(f"Source changed during copy: {source}")

    atomic_write(target, copy)


@contextmanager
def file_lock(path: Path):
    """Hold a process-safe publication lease, failing immediately if it is busy."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise BlockingIOError(f"Resource is busy: {path}") from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
