"""Stable SHA-256 helpers for files and directory trees."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from fnmatch import fnmatchcase
from functools import partial
from pathlib import Path
from typing import Protocol

_CHUNK_SIZE = 1024 * 1024


class _Digest(Protocol):
    def update(self, data: bytes, /) -> None: ...


def _update_from_file(digest: _Digest, path: Path) -> int:
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(partial(stream.read, _CHUNK_SIZE), b""):
            digest.update(chunk)
            size += len(chunk)
    return size


def file_sha256(path: Path) -> str:
    """Return the SHA-256 digest of a file's contents."""
    digest = hashlib.sha256()
    _update_from_file(digest, Path(path))
    return digest.hexdigest()


def directory_sha256(path: Path, ignored_parts: Iterable[str] = ()) -> str:
    """Hash relative paths and contents in stable order.

    Each ignored value is matched against every relative path component and may
    be either a literal name or a shell-style pattern such as ``*.egg-info``. A
    leading ``/`` anchors the pattern to the top level, so ``/build`` skips the
    setuptools output directory at the root without also skipping a package that
    happens to keep source in a directory called ``build``.
    """
    root = Path(path).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(root)
    if not root.is_dir():
        raise NotADirectoryError(root)
    patterns = tuple(ignored_parts)

    def ignored(item: Path) -> bool:
        parts = item.relative_to(root).parts
        for pattern in patterns:
            if pattern.startswith("/"):
                if parts and fnmatchcase(parts[0], pattern[1:]):
                    return True
            elif any(fnmatchcase(part, pattern) for part in parts):
                return True
        return False

    digest = hashlib.sha256()
    for item in sorted(root.rglob("*")):
        if ignored(item):
            continue
        if item.is_symlink():
            raise ValueError(
                f"Directory hash does not allow symlinks: {item.relative_to(root)}"
            )
        if not item.is_file():
            continue
        relative = item.relative_to(root).as_posix().encode("utf-8")
        size = item.stat().st_size
        digest.update(b"F")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(size.to_bytes(8, "big"))
        if _update_from_file(digest, item) != size:
            raise OSError(f"File changed while hashing: {item}")
    return digest.hexdigest()
