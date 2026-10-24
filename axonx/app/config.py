"""Typed application and Studio configuration owned by the service."""

from __future__ import annotations

import re
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..config.models import RuntimeConfig, ComponentConfig, JobConfig, PluginConfig
from ..config.target import TargetConfig, normalize_target
from ..config.defaults import AXONX_NAME, DEFAULT_TRANSFER_BUDGET_BYTES
from ..task.enums import TaskCategory


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


class ApplicationConfig(RuntimeConfig):
    """Describe one complete AxonX application instance."""

    model_config = ConfigDict(extra="forbid")
    app_name: str = AXONX_NAME
    transfer_budget_bytes: int = Field(default=DEFAULT_TRANSFER_BUDGET_BYTES, gt=0, strict=True)
    language: Literal["en", "zh"] = "en"
    enable_logo: bool = True
    log_to_console: bool = True
    log_to_file: bool = True
    plugins: PluginConfig = Field(default_factory=PluginConfig)
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
