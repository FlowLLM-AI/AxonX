"""Validated response contracts for machine Steps."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MachineModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AxonxInfo(MachineModel):
    version: str = Field(min_length=1)
    git_commit: str | None = None
    git_branch: str | None = None


class CpuInfo(MachineModel):
    total_cores: int | None = Field(default=None, ge=1)
    physical_cores: int | None = Field(default=None, ge=1)
    usage_percent: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def validate_core_counts(self) -> "CpuInfo":
        if (
            self.total_cores is not None
            and self.physical_cores is not None
            and self.physical_cores > self.total_cores
        ):
            raise ValueError("physical_cores cannot exceed total_cores")
        return self


class MemoryInfo(MachineModel):
    total_bytes: int = Field(ge=0)
    used_bytes: int = Field(ge=0)
    available_bytes: int = Field(ge=0)
    usage_percent: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def validate_capacity(self) -> "MemoryInfo":
        if self.used_bytes > self.total_bytes:
            raise ValueError("used_bytes cannot exceed total_bytes")
        if self.available_bytes > self.total_bytes:
            raise ValueError("available_bytes cannot exceed total_bytes")
        return self


class GpuInfo(MachineModel):
    vendor: Literal["nvidia", "amd"]
    index: int = Field(ge=0)
    uuid: str | None = None
    name: str | None = None
    memory_total_bytes: int | None = Field(default=None, ge=0)
    memory_used_bytes: int | None = Field(default=None, ge=0)
    memory_available_bytes: int | None = Field(default=None, ge=0)
    memory_usage_percent: float | None = Field(default=None, ge=0, le=100)
    usage_percent: float | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def validate_memory_capacity(self) -> "GpuInfo":
        if self.memory_total_bytes is None:
            return self
        if (
            self.memory_used_bytes is not None
            and self.memory_used_bytes > self.memory_total_bytes
        ):
            raise ValueError("memory_used_bytes cannot exceed memory_total_bytes")
        if (
            self.memory_available_bytes is not None
            and self.memory_available_bytes > self.memory_total_bytes
        ):
            raise ValueError("memory_available_bytes cannot exceed memory_total_bytes")
        return self


class MachineInfo(MachineModel):
    axonx: AxonxInfo
    cpu: CpuInfo
    memory: MemoryInfo
    gpus: list[GpuInfo] = Field(default_factory=list)


class MachineHealth(MachineModel):
    address: str = Field(min_length=1)
    healthy: bool


class ShellOutput(MachineModel):
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = 0
    stdout_truncated: bool = False
    stderr_truncated: bool = False
