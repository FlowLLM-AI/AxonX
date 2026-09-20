"""Validated models for one AxonX application configuration."""

from __future__ import annotations

from ipaddress import ip_address
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..constants import (
    AXONX_DEFAULT_LOG_DIR,
    AXONX_DEFAULT_TIMEZONE,
    AXONX_NAME,
)


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


__all__ = [
    "ApplicationConfig",
    "ComponentConfig",
    "JobConfig",
    "PluginConfig",
    "RemoteNode",
    "ScheduleConfig",
]
