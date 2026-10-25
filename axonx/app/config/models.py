"""Typed application, component, Job, target and Studio configuration."""

from __future__ import annotations

import re
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ...common.connection import normalize_target
from ...common.constants import DEFAULT_TRANSFER_BUDGET_BYTES
from ...common.runtime import RuntimeSettings
from ...task.enums import TaskCategory


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


class StudioPageConfig(BaseModel):
    """One service-defined page, grouping root Task runs by category."""

    model_config = ConfigDict(extra="forbid")
    title: dict[Literal["en", "zh"], str]
    view: Literal["tasks", "pipeline"]
    category: TaskCategory

    @model_validator(mode="after")
    def validate_page(self) -> Self:
        if set(self.title) != {"en", "zh"} or any(not title.strip() for title in self.title.values()):
            raise ValueError("Studio page titles require non-empty en and zh translations")
        return self


class StudioPage(StudioPageConfig):
    id: str


class StudioConfig(BaseModel):
    """Business navigation supplied by the application, independent of the framework."""

    model_config = ConfigDict(extra="forbid")
    pages: dict[str, StudioPageConfig] = Field(default_factory=dict)

    @field_validator("pages")
    @classmethod
    def validate_page_ids(cls, pages: dict[str, StudioPageConfig]) -> dict[str, StudioPageConfig]:
        if any(not re.fullmatch(r"[a-z][a-z0-9_-]*", name) for name in pages):
            raise ValueError("Studio page IDs must be lowercase URL slugs")
        return pages


class ApplicationConfig(RuntimeSettings):
    """Describe one complete AxonX application instance."""

    model_config = ConfigDict(extra="forbid")
    cron: str | None = Field(default=None, min_length=1)
    app_name: str = "AxonX"
    transfer_budget_bytes: int = Field(default=DEFAULT_TRANSFER_BUDGET_BYTES, gt=0, strict=True)
    language: Literal["en", "zh"] = "en"
    enable_logo: bool = True
    log_to_console: bool = True
    log_to_file: bool = True
    targets: list[TargetConfig] = Field(default_factory=list)
    components: dict[str, dict[str, ComponentConfig]] = Field(default_factory=dict)
    jobs: dict[str, JobConfig] = Field(default_factory=dict)
    studio: StudioConfig = Field(default_factory=StudioConfig)
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
