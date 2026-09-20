"""Parse, load, inherit, merge, and resolve application configuration."""

import json
import os
import re
from collections.abc import Mapping
from importlib.metadata import EntryPoint
from ipaddress import ip_address
from pathlib import Path
from typing import Any, Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..constants import (
    AXONX_DEFAULT_ENCODING,
    AXONX_DEFAULT_LOG_DIR,
    AXONX_DEFAULT_TIMEZONE,
    AXONX_NAME,
    CONFIG_ENTRY_POINT_GROUP,
)
from .entry_points import (
    find_entry_points,
    load_entry_point,
    unique_entry_point,
)

_CONFIG_DIR = Path(__file__).parent
_SUPPORTED_EXTENSIONS = (".yaml", ".yml", ".json")
_ENV_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?}")
_LEADING_ZERO_RE = re.compile(r"^-?0\d")


class ComponentConfig(BaseModel):
    """Select a component backend and retain backend-specific options."""

    model_config = ConfigDict(extra="allow")
    backend: str = Field(min_length=1)


class JobConfig(ComponentConfig):
    """Configure a Job's public contract and ordered Steps."""

    backend: str = Field(default="pipeline", min_length=1)
    description: str = ""
    parameters: dict[str, Any] = Field(
        default_factory=lambda: {"type": "object", "properties": {}}
    )
    enable_serve: bool = True
    enable_remote: bool = True
    enable_stream: bool = True
    requires_auth: bool = False
    steps: list[ComponentConfig] = Field(default_factory=list)
    defaults: dict[str, Any] = Field(default_factory=dict)

    @field_validator("parameters")
    @classmethod
    def validate_parameters(cls, value: dict[str, Any]) -> dict[str, Any]:
        schema = {**value}
        schema.setdefault("type", "object")
        if schema["type"] != "object":
            raise ValueError("job parameters must describe a JSON object")
        return schema


class ScheduleConfig(ComponentConfig):
    """Configure one trigger that invokes a named Job."""

    backend: str = Field(default="cron", min_length=1)
    job: str = Field(min_length=1)
    cron: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    timezone: str | None = Field(default=None, min_length=1)
    concurrency_policy: Literal["forbid", "allow", "replace"] = "forbid"


class PluginConfig(BaseModel):
    """Configure startup plugin sources and privileged remote mutation."""

    model_config = ConfigDict(extra="forbid")
    sources: list[str] = Field(default_factory=list)
    allow_remote_management: bool = False

    @field_validator("sources")
    @classmethod
    def validate_sources(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("Plugin source paths must be non-empty strings")
        return values


class RemoteNode(BaseModel):
    """Address of a configured remote AxonX node."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    host_ip: str = Field(min_length=1)
    host_port: int = Field(ge=1, le=65535)
    token: str | None = Field(default=None, min_length=1, repr=False)

    @field_validator("host_ip")
    @classmethod
    def validate_host_ip(cls, value: str) -> str:
        return ip_address(value).compressed

    @property
    def address(self) -> str:
        host = f"[{self.host_ip}]" if ":" in self.host_ip else self.host_ip
        return f"{host}:{self.host_port}"


class ApplicationConfig(BaseModel):
    """Describe one complete AxonX application instance."""

    model_config = ConfigDict(extra="forbid")
    app_name: str = AXONX_NAME
    workspace_dir: str = ".axonx"
    log_dir: str = AXONX_DEFAULT_LOG_DIR
    timezone: str = AXONX_DEFAULT_TIMEZONE
    enable_logo: bool = True
    log_to_console: bool = True
    log_to_file: bool = True
    plugins: PluginConfig = Field(default_factory=PluginConfig)
    remote_nodes: list[RemoteNode] = Field(default_factory=list)
    environment: dict[str, str] = Field(default_factory=dict)
    components: dict[str, dict[str, ComponentConfig]] = Field(default_factory=dict)
    jobs: dict[str, JobConfig] = Field(default_factory=dict)
    schedules: dict[str, ScheduleConfig] = Field(default_factory=dict)
    service: ComponentConfig | None = None

    @model_validator(mode="after")
    def validate_remote_nodes(self) -> Self:
        addresses = [node.host_ip for node in self.remote_nodes]
        if len(addresses) != len(set(addresses)):
            raise ValueError("Remote node IPs must be unique")
        return self

    def resolve_remote_node(self, remote_ip: str) -> RemoteNode:
        try:
            normalized_ip = ip_address(remote_ip).compressed
        except ValueError as exc:
            raise ValueError(f"Invalid remote IP: {remote_ip!r}") from exc
        for node in self.remote_nodes:
            if node.host_ip == normalized_ip:
                return node
        raise ValueError(f"Remote AxonX is not configured: {normalized_ip!r}")


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
) -> dict:
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
        encoding: str = AXONX_DEFAULT_ENCODING,
    ) -> None:
        self.config_dir = Path(config_dir)
        self.encoding = encoding
        self.registry = self._discover_configs()

    def _discover_configs(self) -> dict[str, Path]:
        if not self.config_dir.is_dir():
            return {}
        files = sorted(
            (
                path
                for path in self.config_dir.iterdir()
                if path.is_file() and path.suffix in _SUPPORTED_EXTENSIONS
            ),
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

        entry = unique_entry_point(external_entries, name_or_path, "Config")
        external = self._external_config_path(name_or_path, entry)
        if external is not None:
            return external

        path = Path(name_or_path)
        if path.suffix in _SUPPORTED_EXTENSIONS:
            candidates = (
                (path,) if path.is_absolute() else (path, self.config_dir / path)
            )
            for candidate in candidates:
                if candidate.is_file():
                    return candidate
            raise FileNotFoundError(f"Config file not found: {path}")

        known = ", ".join(sorted(self.registry)) or "none"
        raise FileNotFoundError(
            f"Config file not found: {name_or_path}. Available: {known}",
        )

    def _read(self, path: Path) -> dict:
        with path.open(encoding=self.encoding) as file:
            config = json.load(file) if path.suffix == ".json" else yaml.safe_load(file)
        if config is None:
            return {}
        if not isinstance(config, dict):
            raise ValueError(f"Config root must be a mapping/object: {path}")
        config = expand_env_vars(config)
        plugins = config.get("plugins")
        if isinstance(plugins, dict) and isinstance(plugins.get("sources"), list):
            plugins["sources"] = [
                (
                    str((path.parent / plugin).resolve())
                    if isinstance(plugin, str)
                    and not Path(plugin).expanduser().is_absolute()
                    else plugin
                )
                for plugin in plugins["sources"]
            ]
        return config

    def _load(
        self,
        name_or_path: str,
        stack: tuple[tuple[str, str], ...],
    ) -> dict:
        path = self._locate(name_or_path)
        identity = str(path.resolve())
        if identity in {item[0] for item in stack}:
            chain = " -> ".join((*[item[1] for item in stack], name_or_path))
            raise ValueError(f"Circular config inheritance: {chain}")

        config = self._read(path)
        raw_parents = config.pop("extends", ())
        parents = (
            (raw_parents,) if isinstance(raw_parents, str) else tuple(raw_parents or ())
        )
        merged: dict = {}
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

    def load(self, name_or_path: str | Path) -> dict:
        """Load one named or path-based configuration, including its parents."""
        return self._load(str(name_or_path), ())

    def resolve(self, *, log_config: bool = True, **overrides) -> dict:
        """Resolve a selected/default configuration and apply explicit overrides."""
        from ..utils import get_logger

        source = overrides.get("config")
        base: dict = {}
        if isinstance(source, str):
            overrides.pop("config")
            if log_config:
                get_logger().info(f"Loading config: {source}")
            base = self.load(source)
        elif "default" in self.registry:
            if log_config:
                get_logger().info(
                    "No config specified, loading 'default'",
                )
            base = self.load("default")
        return deep_merge_config(base, overrides)


def resolve_app_config(*, log_config: bool = True, **kwargs) -> dict:
    """Resolve application configuration using the built-in config directory."""
    return ConfigResolver().resolve(log_config=log_config, **kwargs)
