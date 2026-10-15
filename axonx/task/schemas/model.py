"""Portable model collections and their declared artifact references."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ...enums import TaskType
from .artifact import ArtifactRecord
from .protocol import Protocol, validate_protocol


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
