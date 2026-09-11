"""Validated application, component, and job configuration models."""

from ipaddress import ip_address
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..constants import AXONX_NAME


class ComponentConfig(BaseModel):
    """Select a component backend and retain backend-specific options."""

    model_config = ConfigDict(extra="allow")
    backend: str = Field(min_length=1)


class JobConfig(ComponentConfig):
    """Configure a job's schema, defaults, visibility, and ordered steps."""

    backend: str = Field(default="base", min_length=1)
    description: str = Field(default="")
    parameters: dict[str, Any] = Field(default_factory=lambda: {"type": "object", "properties": {}})
    enable_serve: bool = True
    steps: list[ComponentConfig] = Field(default_factory=list)
    defaults: dict[str, Any] = Field(default_factory=dict)

    @field_validator("parameters")
    @classmethod
    def validate_parameters(cls, value: dict[str, Any]) -> dict[str, Any]:
        """Require job parameters to describe a JSON object."""
        schema = {**value}
        schema.setdefault("type", "object")
        if schema["type"] != "object":
            raise ValueError("job parameters must describe a JSON object")
        return schema


class RemoteNode(BaseModel):
    """Address of a configured remote AxonX node."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    host_ip: str = Field(min_length=1)
    host_port: int = Field(ge=1, le=65535)

    @field_validator("host_ip")
    @classmethod
    def validate_host_ip(cls, value: str) -> str:
        ip_address(value)
        return value

    @property
    def address(self) -> str:
        host = f"[{self.host_ip}]" if ":" in self.host_ip else self.host_ip
        return f"{host}:{self.host_port}"


class ApplicationConfig(BaseModel):
    """Describe one complete AxonX application instance."""

    model_config = ConfigDict(extra="forbid")
    app_name: str = AXONX_NAME
    workspace_dir: str = ".axonx"
    timezone: str = "Asia/Shanghai"
    plugins: list[str] = Field(default_factory=list)
    remote_nodes: list[RemoteNode] = Field(default_factory=list)
    environment: dict[str, str] = Field(default_factory=dict)
    components: dict[str, dict[str, ComponentConfig]] = Field(default_factory=dict)
    jobs: dict[str, JobConfig] = Field(default_factory=dict)
    service: ComponentConfig | None = None

    @field_validator("plugins")
    @classmethod
    def validate_plugin_paths(cls, values: list[str]) -> list[str]:
        """Plugins are configured only by non-empty local project paths."""
        if any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError("Plugin paths must be non-empty strings")
        return values
