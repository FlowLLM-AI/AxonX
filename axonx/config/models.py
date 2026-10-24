"""Declarative provider and runtime configuration, independent of application code."""

from typing import Any
from pydantic import BaseModel, ConfigDict, Field, field_validator
from ..common.constants import AXONX_DEFAULT_LOG_DIR, AXONX_DEFAULT_TIMEZONE


class RuntimeConfig(BaseModel):
    """Settings shared by execution and scheduler processes, without service models."""

    model_config = ConfigDict(extra="ignore")
    workspace_dir: str = ".axonx"
    log_dir: str = AXONX_DEFAULT_LOG_DIR
    timezone: str = AXONX_DEFAULT_TIMEZONE
    environment: dict[str, str] = Field(default_factory=dict)
    cron: str | None = Field(default=None, min_length=1)


class ComponentConfig(BaseModel):
    """Select a component backend and retain backend-specific options."""

    model_config = ConfigDict(extra="allow")
    backend: str = Field(min_length=1)


class JobConfig(ComponentConfig):
    """Configure a Job's public contract and ordered Steps."""

    backend: str = Field(default="pipeline", min_length=1)
    description: str = ""
    parameters: dict[str, Any] = Field(default_factory=lambda: {"type": "object", "properties": {}})
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


class PluginConfig(BaseModel):
    """Configure startup plugin sources."""

    model_config = ConfigDict(extra="forbid")
    sources: list[str] = Field(default_factory=list)

    @field_validator("sources")
    @classmethod
    def validate_sources(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("Plugin source paths must be non-empty strings")
        return values
