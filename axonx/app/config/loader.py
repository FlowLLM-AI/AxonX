"""Load application configuration from files, bundled names or installed packages."""

import json
from collections.abc import Mapping
from importlib import import_module, metadata
from pathlib import Path
from typing import Any

import yaml

_SUPPORTED_EXTENSIONS = (".yaml", ".yml", ".json")


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


class ConfigLoader:
    """Resolve application configuration with ordered inheritance and overrides.

    Mappings merge recursively; lists and scalar values are replaced. Installed
    ``axonx.configs`` entries name a package and an optional configuration stem.
    """

    def __init__(self, config_dir: Path | str = Path(__file__).parent) -> None:
        self.config_dir = Path(config_dir).expanduser().resolve()

    @staticmethod
    def _named_file(directory: Path, name: str) -> Path | None:
        for suffix in _SUPPORTED_EXTENSIONS:
            path = directory / f"{name}{suffix}"
            if path.is_file():
                return path
        return None

    def _locate(self, source: str | Path) -> Path:
        if not isinstance(source, (str, Path)) or not str(source).strip():
            raise ValueError("Config source must be a non-empty name or path")
        name = str(source)
        path = Path(source).expanduser()
        if path.suffix in _SUPPORTED_EXTENSIONS:
            for candidate in ((path,) if path.is_absolute() else (path, self.config_dir / path)):
                if candidate.is_file():
                    return candidate.resolve()
        else:
            builtin = self._named_file(self.config_dir, name)
            entries = metadata.entry_points(group="axonx.configs", name=name)
            if builtin is not None and entries:
                raise ValueError(f"Config '{name}' is provided by both AxonX and an installed distribution")
            if len(entries) > 1:
                raise ValueError(f"Config '{name}' has multiple installed providers")
            if builtin is not None:
                return builtin.resolve()
            if entries:
                entry = next(iter(entries))
                locations = tuple(getattr(import_module(entry.module), "__path__", ()))
                if len(locations) != 1:
                    raise ValueError(f"Config entry point '{name}' must target one package directory")
                installed = self._named_file(Path(locations[0]), entry.attr or name)
                if installed is None:
                    raise ValueError(f"Config entry point '{name}' did not resolve to a supported file")
                return installed.resolve()
        raise FileNotFoundError(f"Config file not found: {source}")

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        from ...utils.env import expand_env_vars

        with path.open(encoding="utf-8") as file:
            config = json.load(file) if path.suffix == ".json" else yaml.safe_load(file)
        if config is None:
            return {}
        if not isinstance(config, dict):
            raise ValueError(f"Config root must be a mapping/object: {path}")
        return expand_env_vars(config)

    def _load(
        self,
        source: str | Path,
        stack: tuple[Path, ...],
    ) -> dict[str, Any]:
        path = self._locate(source)
        if path in stack:
            chain = " -> ".join(str(item) for item in (*stack, path))
            raise ValueError(f"Circular config inheritance: {chain}")

        config = self._read(path)
        parents = config.pop("extends", [])
        if isinstance(parents, str):
            parents = [parents]
        if not isinstance(parents, list) or any(not isinstance(item, str) or not item.strip() for item in parents):
            raise ValueError(f"Config 'extends' must be a non-empty string or a list of non-empty strings: {path}")
        merged: dict[str, Any] = {}

        for parent in parents:
            relative = path.parent / Path(parent).expanduser()
            parent_source = relative if relative.is_file() else parent
            merged = deep_merge_config(merged, self._load(parent_source, (*stack, path)))
        return deep_merge_config(merged, config)

    def load(self, source: str | Path) -> dict[str, Any]:
        """Load one named or path-based configuration, including its parents."""
        return self._load(source, ())

    def resolve(
        self,
        *,
        config: str | Path | None = None,
        log_config: bool = True,
        **overrides: Any,
    ) -> dict[str, Any]:
        """Resolve a selected/default configuration and apply explicit overrides."""
        from ...utils.logging import get_logger

        source = "default" if config is None else config
        if log_config:
            get_logger().info(f"Loading config: {source}")
        return deep_merge_config(self.load(source), overrides)
