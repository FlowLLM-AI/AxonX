"""Parse, load, inherit, merge, and resolve application configuration."""

import json
import os
import re
from collections.abc import Mapping
from importlib.metadata import EntryPoint
from pathlib import Path
from typing import Any

import yaml

from ..constants import CONFIG_ENTRY_POINT_GROUP
from ..utils.entry_points import (
    find_entry_points,
    load_entry_point,
    unique_entry_point,
)

_CONFIG_DIR = Path(__file__).parent
_SUPPORTED_EXTENSIONS = (".yaml", ".yml", ".json")
_ENV_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?}")
_LEADING_ZERO_RE = re.compile(r"^-?0\d")


def convert_value(value: str) -> Any:
    """Convert a textual configuration value to its natural Python value."""
    value = value.strip()
    lower = value.lower()
    if lower in {"none", "null"}:
        return None
    if lower in {"true", "false"}:
        return lower == "true"

    if not _LEADING_ZERO_RE.match(value):
        for converter in (int, float):
            try:
                return converter(value)
            except ValueError:
                pass

    try:
        return json.loads(value)
    except ValueError:
        return value


def expand_env_vars(value: Any, env: Mapping[str, str] | None = None) -> Any:
    """Recursively expand ``${VAR}`` and ``${VAR:-default}`` placeholders."""
    source = os.environ if env is None else env

    def replace(match: re.Match[str]) -> str:
        name, default = match.group(1), match.group(2)
        if name in source:
            return source[name]
        if default is not None:
            return default
        raise ValueError(f"Config references undefined env var: {name}")

    if isinstance(value, str):
        expanded = _ENV_VAR_RE.sub(replace, value)
        return convert_value(expanded) if expanded != value else value
    if isinstance(value, dict):
        return {key: expand_env_vars(item, source) for key, item in value.items()}
    if isinstance(value, list):
        return [expand_env_vars(item, source) for item in value]
    return value


def deep_merge_config(
    base: Mapping[str, Any],
    update: Mapping[str, Any],
) -> dict[str, Any]:
    """Recursively merge mappings without mutating either input."""
    result = dict(base)
    for key, value in update.items():
        if isinstance(result.get(key), Mapping) and isinstance(value, Mapping):
            result[key] = deep_merge_config(result[key], value)
        else:
            result[key] = value
    return result


class ConfigResolver:
    """Discover configuration files and resolve inheritance and overrides."""

    def __init__(
        self,
        config_dir: Path | str = _CONFIG_DIR,
        *,
        encoding: str = "utf-8",
    ) -> None:
        self.config_dir = Path(config_dir)
        self.encoding = encoding
        self.registry = self._discover_configs()

    def _discover_configs(self) -> dict[str, Path]:
        if not self.config_dir.is_dir():
            return {}
        files = sorted(
            (path for path in self.config_dir.iterdir() if path.is_file() and path.suffix in _SUPPORTED_EXTENSIONS),
            key=lambda path: (_SUPPORTED_EXTENSIONS.index(path.suffix), path.name),
        )
        return {path.stem: path for path in reversed(files)}

    def _external_config_path(self, name: str, entry: EntryPoint | None) -> Path | None:
        if entry is None:
            return None
        path = Path(load_entry_point(entry, invoke=True))
        if path.suffix not in _SUPPORTED_EXTENSIONS or not path.is_file():
            raise ValueError(
                f"Config entry point '{name}' did not resolve to a YAML or JSON file",
            )
        return path

    def _locate(self, name_or_path: str) -> Path:
        built_in = self.registry.get(name_or_path)
        external_entries = find_entry_points(CONFIG_ENTRY_POINT_GROUP, name_or_path)
        if built_in is not None and external_entries:
            raise ValueError(
                f"Config '{name_or_path}' is provided by both AxonX and an installed distribution",
            )
        if built_in is not None:
            return built_in

        entry = unique_entry_point(external_entries, name_or_path, provider="Config")
        external = self._external_config_path(name_or_path, entry)
        if external is not None:
            return external

        path = Path(name_or_path)
        if path.suffix in _SUPPORTED_EXTENSIONS:
            candidates = (path,) if path.is_absolute() else (path, self.config_dir / path)
            for candidate in candidates:
                if candidate.is_file():
                    return candidate
            raise FileNotFoundError(f"Config file not found: {path}")

        known = ", ".join(sorted(self.registry)) or "none"
        raise FileNotFoundError(
            f"Config file not found: {name_or_path}. Available: {known}",
        )

    def _read(self, path: Path) -> dict[str, Any]:
        with path.open(encoding=self.encoding) as file:
            config = json.load(file) if path.suffix == ".json" else yaml.safe_load(file)
        if config is None:
            return {}
        if not isinstance(config, dict):
            raise ValueError(f"Config root must be a mapping/object: {path}")
        return expand_env_vars(config)

    def _load(
        self,
        name_or_path: str,
        stack: tuple[tuple[str, str], ...],
    ) -> dict[str, Any]:
        path = self._locate(name_or_path)
        identity = str(path.resolve())
        if identity in {item[0] for item in stack}:
            chain = " -> ".join((*[item[1] for item in stack], name_or_path))
            raise ValueError(f"Circular config inheritance: {chain}")

        config = self._read(path)
        raw_parents = config.pop("extends", ())
        parents = (raw_parents,) if isinstance(raw_parents, str) else tuple(raw_parents or ())
        merged: dict[str, Any] = {}
        next_stack = (*stack, (identity, name_or_path))

        for parent in parents:
            if not isinstance(parent, str) or not parent:
                raise ValueError(
                    f"Config 'extends' entries must be non-empty strings: {path}",
                )
            relative = path.parent / parent
            parent_source = str(relative.resolve()) if relative.is_file() else parent
            merged = deep_merge_config(merged, self._load(parent_source, next_stack))
        return deep_merge_config(merged, config)

    def load(self, name_or_path: str | Path) -> dict[str, Any]:
        """Load one named or path-based configuration, including its parents."""
        return self._load(str(name_or_path), ())

    def resolve(self, *, log_config: bool = True, **overrides: Any) -> dict[str, Any]:
        """Resolve a selected/default configuration and apply explicit overrides."""
        from ..utils import get_logger

        source = overrides.get("config")
        base: dict[str, Any] = {}
        if isinstance(source, str):
            overrides.pop("config")
            if log_config:
                get_logger(log_to_file=False).info(f"Loading config: {source}")
            base = self.load(source)
        elif "default" in self.registry:
            if log_config:
                get_logger(log_to_file=False).info(
                    "No config specified, loading 'default'",
                )
            base = self.load("default")
        return deep_merge_config(base, overrides)


def resolve_app_config(*, log_config: bool = True, **kwargs: Any) -> dict[str, Any]:
    """Resolve application configuration using the built-in config directory."""
    return ConfigResolver().resolve(log_config=log_config, **kwargs)
