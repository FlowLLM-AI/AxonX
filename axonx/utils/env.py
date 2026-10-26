"""Explicit environment loading and recursive variable expansion."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .values import convert_value

_ENV_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?}")


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
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key := key.strip():
            values[key] = value.strip().strip("'\"")
    return values


def load_env(
    path: str | Path | None = None,
    *,
    override: bool = False,
    search_depth: int = 5,
) -> dict[str, str]:
    """Load a file and return its keys with their effective environment values."""
    env_path = Path(path) if path is not None else find_env_file(search_depth=search_depth)
    if env_path is None or not env_path.is_file():
        return {}
    values = parse_env_file(env_path)
    os.environ.update({key: value for key, value in values.items() if override or key not in os.environ})
    return {key: os.environ[key] for key in values}


def expand_env_vars(value: Any, env: Mapping[str, str] | None = None) -> Any:
    """Expand ``${VAR}`` and ``${VAR:-default}``, converting changed scalar values."""
    source = os.environ if env is None else env

    def replace(match: re.Match[str]) -> str:
        name, default = match.group(1), match.group(2)
        if name in source:
            return source[name]
        if default is not None:
            return default
        raise ValueError(f"Undefined environment variable: {name}")

    if isinstance(value, str):
        expanded = _ENV_VAR_RE.sub(replace, value)
        return convert_value(expanded) if expanded != value else value
    if isinstance(value, dict):
        return {key: expand_env_vars(item, source) for key, item in value.items()}
    if isinstance(value, list):
        return [expand_env_vars(item, source) for item in value]
    return value
