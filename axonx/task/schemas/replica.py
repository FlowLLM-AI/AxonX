"""A display replica records actual files without changing source research semantics."""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class ReplicaFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    size: int = Field(ge=0)
    revision: str = Field(min_length=1)
    sampled: bool = False
    rows: int | None = Field(default=None, ge=0)
    source_rows: int | None = Field(default=None, ge=0)
    dates: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def read_legacy(cls, value):
        if isinstance(value, dict) and "sha256" in value:
            value = dict(value)
            value.setdefault("revision", "legacy:" + value.pop("sha256"))
        return value


class LiveSnapshot(BaseModel):
    """One ordered, read-only snapshot of an exact parent Run and its children."""

    model_config = ConfigDict(extra="forbid")
    source_id: str = Field(min_length=1)
    root_task_id: str = Field(min_length=1)
    root_run_id: str = Field(min_length=1)
    captured_at: AwareDatetime
    revision: int = Field(gt=0)


class ReplicaLog(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)


class DisplayReplica(BaseModel):
    model_config = ConfigDict(extra="forbid")
    purpose: Literal["display"] = "display"
    source_revision: str = Field(min_length=1)
    policy_revision: str = Field(min_length=1)
    files: dict[str, ReplicaFile]
    omitted: dict[str, str] = Field(default_factory=dict)
    source_log_path: str = ""
    snapshot: LiveSnapshot | None = None
    log: ReplicaLog | None = None

    @model_validator(mode="before")
    @classmethod
    def read_legacy(cls, value):
        if isinstance(value, dict):
            value = dict(value)
            for old, new in (
                ("source_digest", "source_revision"),
                ("policy_digest", "policy_revision"),
            ):
                if old in value:
                    value.setdefault(new, "legacy:" + value.pop(old))
        return value
