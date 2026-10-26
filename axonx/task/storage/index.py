"""Read-only incremental metadata scans that never descend into Task artifacts."""

import os
import stat
from pathlib import Path

from ..models.lifecycle import TaskMetadata
from .workspace import (
    METADATA_FILE,
    kind_directories,
    parse_task_directory,
    read_task_metadata,
)

FileVersion = tuple[int, int, int, int]


def scan_metadata(
    root: Path,
    previous: dict[str, TaskMetadata],
    versions: dict[str, FileVersion],
) -> tuple[dict[str, TaskMetadata], dict[str, FileVersion]]:
    """Reuse unchanged records; propagate I/O errors before replacing the index."""
    entries = {}
    current = {}
    for parent in kind_directories(root):
        try:
            if not stat.S_ISDIR(parent.lstat().st_mode):
                continue
            children = os.scandir(parent)
        except FileNotFoundError:
            continue
        with children:
            for child in children:
                if not child.is_dir(follow_symlinks=False):
                    continue
                try:
                    parse_task_directory(f"{parent.name}/{child.name}")
                except ValueError:
                    continue
                directory = Path(child.path)
                try:
                    info = (directory / METADATA_FILE).lstat()
                except FileNotFoundError:
                    continue
                if not stat.S_ISREG(info.st_mode):
                    continue
                version = (info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
                entry = previous.get(child.name)
                if entry is None or versions.get(child.name) != version:
                    entry = read_task_metadata(directory, child.name, strict_io=True)
                    if entry is None:
                        # An incomplete/invalid write is retried, not treated as deletion.
                        if child.name in previous:
                            entries[child.name] = previous[child.name]
                            if child.name in versions:
                                current[child.name] = versions[child.name]
                        continue
                entries[child.name] = entry
                current[child.name] = version
    return entries, current
