"""Stable SHA-256 helpers for files and directory trees."""

from __future__ import annotations

from collections.abc import Iterable
from fnmatch import fnmatchcase
from functools import partial
import hashlib
from pathlib import Path
from typing import Any

_CHUNK_SIZE = 1024 * 1024


def _update_from_file(digest: Any, path: Path) -> None:
    with path.open("rb") as stream:
        for chunk in iter(partial(stream.read, _CHUNK_SIZE), b""):
            digest.update(chunk)


def file_sha256(path: Path) -> str:
    """Return the SHA-256 digest of a file's contents."""
    digest = hashlib.sha256()
    _update_from_file(digest, Path(path))
    return digest.hexdigest()


def directory_sha256(path: Path, ignored_parts: Iterable[str] = ()) -> str:
    """Hash relative paths and contents in stable order.

    Each ignored value is matched against every relative path component and
    may be either a literal name or a shell-style pattern such as
    ``*.egg-info``.
    """
    root = Path(path).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(root)
    if not root.is_dir():
        raise NotADirectoryError(root)
    patterns = tuple(ignored_parts)

    def ignored(item: Path) -> bool:
        return any(fnmatchcase(part, pattern) for part in item.relative_to(root).parts for pattern in patterns)

    digest = hashlib.sha256()
    for item in sorted(candidate for candidate in root.rglob("*") if candidate.is_file() and not ignored(candidate)):
        relative = item.relative_to(root).as_posix().encode()
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        _update_from_file(digest, item)
    return digest.hexdigest()
