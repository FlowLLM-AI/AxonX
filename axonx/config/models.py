"""Validated models for one AxonX application configuration."""

from __future__ import annotations

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
    """Configure startup plugin sources."""

    model_config = ConfigDict(extra="forbid")
    sources: list[str] = Field(default_factory=list)

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
    "ScheduleConfig",
    "TargetConfig",
]
