"""Portable artifact records, protocol headers, model collections and replay manifests."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from ..task_enums import TaskType


class ArtifactRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    path: str = Field(min_length=1)
    size: int = Field(ge=0)
    revision: str = Field(pattern=r"^\d+:\d+$")

    @field_validator("path")
    @classmethod
    def validate_path(cls, value):
        if value.startswith("/") or "\\" in value or any(part in {"", ".", ".."} for part in value.split("/")):
            raise ValueError("Artifact must be a relative task path")
        return value


PROTOCOL_VERSION = 1


STOCK_SIGNALS_FORMAT = "stock-signals-v1"


class Protocol(BaseModel):
    """Plugins extend the payload; the framework owns version and producer type."""

    model_config = ConfigDict(extra="allow")
    version: Literal[1]
    task_type: TaskType

    @field_validator("version", mode="before")
    @classmethod
    def validate_version(cls, value):
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError("Protocol version must be an integer")
        return value


def task_protocol(task_type: TaskType, **payload: Any) -> dict:
    return Protocol(version=PROTOCOL_VERSION, task_type=task_type, **payload).model_dump(mode="json")


def validate_protocol(value: dict, *task_types: TaskType) -> dict:
    header = Protocol.model_validate(value)
    if task_types and header.task_type not in task_types:
        raise ValueError(f"Expected protocol for {task_types}, got {header.task_type}")
    return value


def fingerprint(value: Mapping) -> str:
    """Hash semantic content deterministically, independent of mapping order."""
    content = json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(content.encode()).hexdigest()


class ModelMember(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_artifact: str = Field(min_length=1)
    model: dict[str, Any]


class ModelCollection(Protocol):
    task_type: Literal[TaskType.TRAIN]
    feature_protocol: dict[str, Any]
    members: dict[str, ModelMember] = Field(min_length=1)
    artifacts: dict[str, ArtifactRecord] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_members(self):
        validate_protocol(self.feature_protocol, TaskType.ETL)
        for member in self.members.values():
            if member.model_artifact not in self.artifacts:
                raise ValueError("Model member references an unregistered artifact")
        return self


class PredictionProtocol(Protocol):
    task_type: Literal[TaskType.PREDICT, TaskType.INFERENCE]
    model_identity: dict[str, str] = Field(min_length=1)
    dates: list[str] = Field(min_length=1)
    score_columns: dict[str, str] = Field(min_length=1)
    predictions_revision: str = Field(pattern=r"^\d+:\d+$")

    @model_validator(mode="after")
    def validate_scope(self):
        if self.dates != sorted(set(self.dates)) or any(not day for day in self.dates):
            raise ValueError("Prediction dates must be nonempty, sorted and unique")
        if any(not key or not value for key, value in self.score_columns.items()):
            raise ValueError("Prediction member IDs and score columns must be nonempty")
        if len(set(self.score_columns.values())) != len(self.score_columns):
            raise ValueError("Prediction members must have distinct score columns")
        return self


class ReplayEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    key: str = Field(min_length=1)
    available_at: AwareDatetime
    files: dict[str, ArtifactRecord]
    attributes: dict[str, Any] = Field(default_factory=dict)


class ReplayManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    version: Literal[1] = 1
    kind: Literal["event_stream"] = "event_stream"
    events: list[ReplayEvent] = Field(min_length=1)
    context: dict[str, ArtifactRecord] = Field(default_factory=dict)
    attributes: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def ordered(self):
        times = [event.available_at for event in self.events]
        if times != sorted(times):
            raise ValueError("Replay events must be ordered by availability")
        return self
