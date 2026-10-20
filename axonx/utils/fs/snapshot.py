"""Atomic snapshots of published files, preserving their revisions."""

import os
import shutil
from pathlib import Path

from .atomic import atomic_write
from .revision import file_revision


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
