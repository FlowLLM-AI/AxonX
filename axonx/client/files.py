"""Build complete directory archives for the workspace file transport."""

import gzip
import io
import json
import os
import tarfile
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

from .config import TAR_PADDING_BYTES

MANIFEST_NAME = "directories.json"


def validate_relative_path(value: str) -> PurePosixPath:
    """Require a canonical, non-root POSIX path without parent traversal."""
    path = PurePosixPath(value)
    if not path.parts or path.is_absolute() or ".." in path.parts or path.as_posix() != value or "\\" in value:
        raise ValueError(f"Invalid file path: {value}")
    return path


def archive_budget(transfer_budget_bytes: int) -> int:
    """Reserve tar padding and gzip overhead inside the transfer budget."""
    return max(0, transfer_budget_bytes - TAR_PADDING_BYTES - max(4096, transfer_budget_bytes // 1024))


def build_file_archive(directories: Mapping[str, Path], target: Path) -> int:
    """Archive complete directories and return their expanded transfer size."""
    for name in directories:
        validate_relative_path(name)
    content = json.dumps(list(directories)).encode()
    with (
        target.open("wb") as raw,
        gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=1) as zipped,
    ):
        with tarfile.open(fileobj=zipped, mode="w") as archive:
            info = tarfile.TarInfo(MANIFEST_NAME)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
            for name, directory in directories.items():
                if directory.is_symlink() or not directory.is_dir():
                    raise ValueError(f"Expected a regular directory: {directory}")
                for path in sorted(directory.rglob("*")):
                    if path.is_symlink():
                        raise ValueError(f"File archives cannot contain symlinks: {path}")
                    if path.is_dir():
                        continue
                    if not path.is_file():
                        raise ValueError(f"Expected a regular file: {path}")
                    with path.open("rb") as stream:
                        before = os.fstat(stream.fileno())
                        info = tarfile.TarInfo(f"{name}/{path.relative_to(directory).as_posix()}")
                        info.size = before.st_size
                        archive.addfile(info, stream)
                        after = os.fstat(stream.fileno())
                    if (before.st_size, before.st_mtime_ns, before.st_ino) != (
                        after.st_size,
                        after.st_mtime_ns,
                        after.st_ino,
                    ) or path.stat() != after:
                        raise OSError(f"File changed while archiving: {path}")
        return zipped.tell()
