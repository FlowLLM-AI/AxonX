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
    description: str = ""
    parameters: dict[str, Any] = Field(
        default_factory=lambda: {"type": "object", "properties": {}},
    )
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


class ApplicationConfig(BaseModel):
    """Describe one complete AxonX application instance."""

    model_config = ConfigDict(extra="forbid")
    app_name: str = AXONX_NAME
    workspace_dir: str = ".axonx"
    timezone: str = "Asia/Shanghai"
    plugins: list[str] = Field(default_factory=list)
    remote_nodes: list[str] = Field(default_factory=list)
    environment: dict[str, str] = Field(default_factory=dict)
    components: dict[str, dict[str, ComponentConfig]] = Field(default_factory=dict)
    jobs: dict[str, JobConfig] = Field(default_factory=dict)
    service: ComponentConfig | None = None

    @field_validator("remote_nodes")
    @classmethod
    def validate_remote_nodes(cls, values: list[str]) -> list[str]:
        """Require each remote AxonX address to use the IP:PORT format."""
        for value in values:
            try:
                host, port = value.rsplit(":", 1)
                ip_address(host.strip("[]"))
                if not 1 <= int(port) <= 65535:
                    raise ValueError
            except (AttributeError, ValueError) as exc:
                raise ValueError(f"Invalid remote AxonX address: {value!r}") from exc
        return values
