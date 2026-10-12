"""A display replica records actual files without changing source research semantics."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ReplicaFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sampled: bool = False
    rows: int | None = Field(default=None, ge=0)
    source_rows: int | None = Field(default=None, ge=0)
    dates: list[str] = Field(default_factory=list)


class DisplayReplica(BaseModel):
    model_config = ConfigDict(extra="forbid")
    purpose: Literal["display"] = "display"
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    files: dict[str, ReplicaFile]
    omitted: dict[str, str] = Field(default_factory=dict)
    source_log_path: str = ""
