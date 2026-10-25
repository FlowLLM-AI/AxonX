"""Scheduled execution windows, inputs and business results."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from .artifacts import ArtifactRecord
from .params import BaseInputParams, BaseOutputParams


class ExecutionWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(min_length=1)
    start_at: AwareDatetime
    end_at: AwareDatetime

    @model_validator(mode="after")
    def validate_range(self):
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at")
        return self


class WindowResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str
    status: Literal["done", "skipped", "incomplete", "failed"]
    reason: str = ""
    commit_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    committed_at: AwareDatetime | None = None
    elapsed_seconds: float = Field(default=0, ge=0)
    rows: int = Field(default=0, ge=0)
    coverage: float | None = Field(default=None, ge=0, le=1)
    artifacts: dict[str, ArtifactRecord] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_commit(self):
        if (self.commit_id is None) != (self.committed_at is None):
            raise ValueError("commit_id and committed_at must be supplied together")
        if self.commit_id is not None and self.status != "done":
            raise ValueError("Only completed windows may publish a commit")
        return self


class WindowOutputParams(BaseOutputParams):
    windows: list[WindowResult] = Field(default_factory=list)


class WindowInputParams(BaseInputParams):
    windows: list[ExecutionWindow] = Field(min_length=1)
    poll_interval_seconds: float = Field(default=1, gt=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_windows(self):
        keys = [window.key for window in self.windows]
        if len(keys) != len(set(keys)):
            raise ValueError("window keys must be unique")
        if self.windows != sorted(self.windows, key=lambda window: window.start_at):
            raise ValueError("windows must be ordered by start_at")
        return self


class BaseInferenceOutputParams(WindowOutputParams):
    model_identity: dict[str, str]
