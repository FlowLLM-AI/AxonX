"""Discover, parse, and apply simple ``.env`` files."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from ..constants import AXONX_DEFAULT_ENCODING


def find_env_file(
    start: str | Path | None = None,
    *,
    search_depth: int = 5,
) -> Path | None:
    """Return the nearest ``.env`` file at or above *start*."""
    if search_depth < 0:
        raise ValueError("search_depth must not be negative")
    origin = Path.cwd() if start is None else Path(start).expanduser()
    directory = origin if origin.is_dir() else origin.parent
    directory = directory.resolve()
    for candidate_dir in (directory, *directory.parents[:search_depth]):
        candidate = candidate_dir / ".env"
        if candidate.is_file():
            return candidate
    return None


def parse_env_file(path: str | Path) -> dict[str, str]:
    """Parse a simple ``KEY=VALUE`` file without changing the environment."""
    values: dict[str, str] = {}
    for line in Path(path).read_text(encoding=AXONX_DEFAULT_ENCODING).splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key := key.strip():
            values[key] = value.strip().strip("'\"")
    return values


def apply_env(
    values: Mapping[str, str],
    *,
    override: bool = False,
) -> dict[str, str]:
    """Apply values and return only entries written to ``os.environ``."""
    applied = {
        key: value for key, value in values.items() if override or key not in os.environ
    }
    os.environ.update(applied)
    return applied


def load_env(
    path: str | Path | None = None,
    *,
    override: bool = False,
    search_depth: int = 5,
) -> dict[str, str]:
    """Load a file and return its keys with their effective environment values."""
    env_path = (
        Path(path) if path is not None else find_env_file(search_depth=search_depth)
    )
    if env_path is None or not env_path.is_file():
        return {}
    values = parse_env_file(env_path)
    apply_env(values, override=override)
    return {key: os.environ[key] for key in values}
