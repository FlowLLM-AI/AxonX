"""Validated models for one AxonX application configuration."""

from __future__ import annotations

from collections.abc import Mapping
from ipaddress import ip_address
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..constants import (
    AXONX_DEFAULT_LOG_DIR,
    AXONX_DEFAULT_TIMEZONE,
    AXONX_NAME,
)
from ..utils.target import normalize_target


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
    enable_stream: bool = True
    requires_auth: bool = True
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
    """Configure startup plugin sources and service-side management."""

    model_config = ConfigDict(extra="forbid")
    sources: list[str] = Field(default_factory=list)
    allow_management: bool = False

    @model_validator(mode="before")
    @classmethod
    def migrate_remote_management(cls, value: Any) -> Any:
        if not isinstance(value, Mapping) or "allow_remote_management" not in value:
            return value
        migrated = dict(value)
        legacy = migrated.pop("allow_remote_management")
        if not migrated.get("allow_management"):
            migrated["allow_management"] = legacy
        return migrated

    @field_validator("sources")
    @classmethod
    def validate_sources(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("Plugin source paths must be non-empty strings")
        return values


class TargetConfig(BaseModel):
    """A configured AxonX service target and its credential."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    address: str = Field(min_length=1)
    token: str | None = Field(default=None, min_length=1, repr=False)

    @field_validator("address")
    @classmethod
    def validate_address(cls, value: str) -> str:
        return normalize_target(value)


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
    targets: list[TargetConfig] = Field(default_factory=list)
    environment: dict[str, str] = Field(default_factory=dict)
    components: dict[str, dict[str, ComponentConfig]] = Field(default_factory=dict)
    jobs: dict[str, JobConfig] = Field(default_factory=dict)
    schedules: dict[str, ScheduleConfig] = Field(default_factory=dict)
    service: ComponentConfig | None = None

    @model_validator(mode="before")
    @classmethod
    def migrate_remote_nodes(cls, value: Any) -> Any:
        if not isinstance(value, Mapping) or "remote_nodes" not in value:
            return value
        migrated = dict(value)
        nodes = migrated.pop("remote_nodes")
        if nodes and migrated.get("targets"):
            raise ValueError("Configure either remote_nodes or targets, not both")
        if nodes:

            def address(node: Mapping[str, Any]) -> str:
                host = node["host_ip"]
                if ":" in host:
                    host = f"[{host}]"
                return f"{host}:{node['host_port']}"

            migrated["targets"] = [
                {
                    "address": address(node),
                    "token": node.get("token"),
                }
                for node in nodes
            ]
            components = migrated.get("components")
            if isinstance(components, Mapping) and isinstance(
                components.get("sync"), Mapping
            ):
                sync = dict(components["sync"])
                for name, spec in sync.items():
                    if not isinstance(spec, Mapping) or "remote_ip" not in spec:
                        continue
                    if "target" in spec:
                        raise ValueError("Sync cannot configure both remote_ip and target")
                    remote_ip = ip_address(spec["remote_ip"])
                    matches = [
                        node
                        for node in nodes
                        if ip_address(node["host_ip"]) == remote_ip
                    ]
                    if len(matches) != 1:
                        raise ValueError(
                            f"Sync remote_ip has no unique remote node: {spec['remote_ip']!r}"
                        )
                    sync[name] = {**spec, "target": address(matches[0])}
                    sync[name].pop("remote_ip")
                migrated["components"] = {**components, "sync": sync}
        return migrated

    @model_validator(mode="after")
    def validate_targets(self) -> Self:
        addresses = [target.address for target in self.targets]
        if len(addresses) != len(set(addresses)):
            raise ValueError("Target addresses must be unique")
        return self

    def resolve_target(self, address: str) -> TargetConfig:
        normalized = normalize_target(address)
        for target in self.targets:
            if target.address == normalized:
                return target
        raise ValueError(f"AxonX target is not configured: {normalized!r}")


__all__ = [
    "ApplicationConfig",
    "ComponentConfig",
    "JobConfig",
    "PluginConfig",
    "TargetConfig",
    "ScheduleConfig",
]
