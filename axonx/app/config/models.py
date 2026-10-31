"""Typed application, Cron, component, Job and target configuration."""

from __future__ import annotations

import re
import shlex
from functools import cached_property
from typing import Any, Literal, Self

from croniter import croniter
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ...client.config import normalize_target

_CRON_FIELD = re.compile(r"^[0-9*,/\-]+$")


class CronConfig(BaseModel):
    """One five-field schedule and a command parsed without a shell."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    expression: str
    command: str

    @field_validator("command", mode="before", json_schema_input_type=str | list[str])
    @classmethod
    def normalize_command(cls, value: Any) -> Any:
        """Join text fragments into one command before tokenizing it."""
        if isinstance(value, list):
            if any(not isinstance(fragment, str) for fragment in value):
                raise ValueError("Command fragments must be strings")
            return " ".join(value)
        return value

    @field_validator("expression")
    @classmethod
    def validate_expression(cls, value: str) -> str:
        fields = value.split()
        if len(fields) != 5 or not all(_CRON_FIELD.fullmatch(field) for field in fields):
            raise ValueError("Expected five numeric cron fields")
        expression = " ".join(fields)
        if not croniter.is_valid(expression):
            raise ValueError(f"Invalid cron expression: {expression}")
        return expression

    @cached_property
    def argv(self) -> tuple[str, ...]:
        """Retain the original command text and parse its argument vector once."""
        return tuple(shlex.split(self.command, comments=False))

    @model_validator(mode="after")
    def validate_command(self) -> Self:
        if not self.argv or not self.argv[0]:
            raise ValueError("A cron entry requires a command")
        return self


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
    workspace_dir: str = ".axonx"
    log_dir: str = "logs"
    timezone: str = "Asia/Shanghai"
    execution_target: str | None = None
    environment: dict[str, str] = Field(default_factory=dict)
    command: tuple[str, ...] = ()
    app_name: str = "AxonX"
    bind_host: str = Field(default="0.0.0.0", min_length=1)
    transfer_budget_bytes: int = Field(default=512 * 1024 * 1024, gt=0, strict=True)
    language: Literal["en", "zh"] = "en"
    enable_logo: bool = True
    log_to_console: bool = True
    log_to_file: bool = True
    targets: list[TargetConfig] = Field(default_factory=list)
    cron: list[CronConfig] = Field(default_factory=list)
    components: dict[str, dict[str, ComponentConfig]] = Field(default_factory=dict)
    jobs: dict[str, JobConfig] = Field(default_factory=dict)
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
