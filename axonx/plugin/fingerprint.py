"""Source-cache, wheel-archive and installed-content SHA-256 fingerprints."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Iterator, Mapping
from fnmatch import fnmatchcase
from functools import partial
from pathlib import Path
from typing import Protocol
from zipfile import ZipFile

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

_CHUNK_SIZE = 1024 * 1024
# Generated/runtime directories are ignored anywhere; build outputs only at
# the project root, preserving source packages with a nested build directory.
_SOURCE_IGNORED_PARTS = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    ".axonx",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".tox",
    ".nox",
    ".DS_Store",
    "/build",
    "/dist",
    "*.egg-info",
}


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


def source_sha256(path: Path) -> str:
    """Hash project source paths and contents for the wheel build cache."""
    root = Path(path).expanduser().resolve()
    if not (root / "pyproject.toml").is_file():
        raise FileNotFoundError(f"Plugin pyproject.toml not found: {root}")

    def ignored(item: Path) -> bool:
        parts = item.relative_to(root).parts
        for pattern in _SOURCE_IGNORED_PARTS:
            if pattern.startswith("/"):
                if parts and fnmatchcase(parts[0], pattern[1:]):
                    return True
            elif any(fnmatchcase(part, pattern) for part in parts):
                return True
        return False

    def files(folder: Path) -> Iterator[Path]:
        for item in sorted(folder.iterdir()):
            if ignored(item):
                continue
            if item.is_symlink():
                raise ValueError(f"Directory hash does not allow symlinks: {item.relative_to(root)}")
            if item.is_dir():
                yield from files(item)
            elif item.is_file():
                yield item

    digest = hashlib.sha256()
    for item in files(root):
        relative = item.relative_to(root).as_posix().encode("utf-8")
        size = item.stat().st_size
        digest.update(b"F")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(size.to_bytes(8, "big"))
        if _update_from_file(digest, item) != size:
            raise OSError(f"File changed while hashing: {item}")
    return digest.hexdigest()


def _record(digest: _Digest, kind: bytes, name: str, value: bytes = b"") -> None:
    encoded = name.encode("utf-8")
    digest.update(kind)
    digest.update(len(encoded).to_bytes(8, "big"))
    digest.update(encoded)
    digest.update(len(value).to_bytes(8, "big"))
    digest.update(value)


def _normalized_requirement(value: str) -> str:
    requirement = Requirement(value)
    extras = ",".join(sorted(requirement.extras))
    return "|".join(
        (
            canonicalize_name(requirement.name),
            extras,
            str(requirement.specifier),
            requirement.url or "",
            str(requirement.marker or ""),
        )
    )


def _identity(
    *,
    distribution: str,
    version: str,
    requirements: Iterable[str],
    plugins: Mapping[str, str],
    files: Iterable[tuple[str, bytes]],
) -> str:
    digest = hashlib.sha256()
    _record(digest, b"D", canonicalize_name(distribution))
    _record(digest, b"V", version)
    for requirement in sorted(_normalized_requirement(value) for value in requirements):
        _record(digest, b"R", requirement)
    for plugin_name, package in sorted(plugins.items()):
        _record(digest, b"E", plugin_name, package.encode("utf-8"))
    for relative, contents in sorted(files):
        _record(digest, b"F", relative, contents)
    return digest.hexdigest()


def _included(relative: Path) -> bool:
    return not ("__pycache__" in relative.parts or relative.suffix == ".pyc")


def content_sha256_from_directories(
    *,
    distribution: str,
    version: str,
    requirements: Iterable[str],
    plugins: Mapping[str, str],
    package_paths: Mapping[str, Path],
) -> str:
    """Hash installed package trees using logical paths rather than host paths."""
    files: dict[str, bytes] = {}
    for package, root in package_paths.items():
        root = Path(root)
        if not root.is_dir():
            raise FileNotFoundError(f"Plugin package directory not found: {root}")
        prefix = package.replace(".", "/")
        for path in root.rglob("*"):
            relative = path.relative_to(root)
            if path.is_file() and _included(relative):
                logical_path = f"{prefix}/{relative.as_posix()}"
                contents = path.read_bytes()
                previous = files.setdefault(logical_path, contents)
                if previous != contents:
                    raise ValueError(f"Conflicting plugin package file: {logical_path}")
    return _identity(
        distribution=distribution,
        version=version,
        requirements=requirements,
        plugins=plugins,
        files=files.items(),
    )


def content_sha256_from_wheel(
    archive: ZipFile,
    *,
    distribution: str,
    version: str,
    requirements: Iterable[str],
    plugins: Mapping[str, str],
) -> str:
    """Hash the same logical plugin contents directly from a wheel archive."""
    prefixes = tuple(f"{package.replace('.', '/')}/" for package in sorted(set(plugins.values())))
    files: dict[str, bytes] = {}
    for entry in archive.infolist():
        name = entry.filename
        if entry.is_dir() or not name.startswith(prefixes):
            continue
        relative = Path(name)
        if _included(relative):
            contents = archive.read(entry)
            previous = files.setdefault(name, contents)
            if previous != contents:
                raise ValueError(f"Conflicting plugin wheel file: {name}")
    return _identity(
        distribution=distribution,
        version=version,
        requirements=requirements,
        plugins=plugins,
        files=files.items(),
    )
