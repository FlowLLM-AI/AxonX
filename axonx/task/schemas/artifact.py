"""Portable artifact identity shared by publications and Task outputs."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
