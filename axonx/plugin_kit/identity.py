"""Stable plugin identities independent of installation and wheel packaging."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from pathlib import Path
from zipfile import ZipFile

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

_IGNORED_PARTS = {"__pycache__"}


def _record(digest, kind: bytes, name: str, value: bytes = b"") -> None:
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
    return not (
        any(part in _IGNORED_PARTS for part in relative.parts)
        or relative.suffix == ".pyc"
    )


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
    prefixes = tuple(
        f"{package.replace('.', '/')}/" for package in sorted(set(plugins.values()))
    )
    files: dict[str, bytes] = {}
    for name in archive.namelist():
        if name.endswith("/") or not name.startswith(prefixes):
            continue
        relative = Path(name)
        if _included(relative):
            contents = archive.read(name)
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
