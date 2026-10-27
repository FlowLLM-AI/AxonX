"""Machine health, diagnostics and execution result models."""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _MachineModel(BaseModel):
    """Shared payload validation and immutability policy."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class BuildInfo(_MachineModel):
    """Version-control identity of the running AxonX build."""

    version: str = Field(min_length=1)
    git_commit: str | None = None
    git_branch: str | None = None


class CpuInfo(_MachineModel):
    """Logical and physical core counts with sampled CPU utilization."""

    total_cores: int | None = Field(default=None, ge=1)
    physical_cores: int | None = Field(default=None, ge=1)
    usage_percent: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def validate_core_counts(self) -> Self:
        if self.total_cores is not None and self.physical_cores is not None and self.physical_cores > self.total_cores:
            raise ValueError("physical_cores cannot exceed total_cores")
        return self


class MemoryInfo(_MachineModel):
    """System memory; available memory can include reclaimable caches."""

    total_bytes: int = Field(ge=0)
    used_bytes: int = Field(ge=0)
    available_bytes: int = Field(ge=0)
    usage_percent: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def validate_capacity(self) -> Self:
        if self.used_bytes > self.total_bytes:
            raise ValueError("used_bytes cannot exceed total_bytes")
        if self.available_bytes > self.total_bytes:
            raise ValueError("available_bytes cannot exceed total_bytes")
        return self


class GpuInfo(_MachineModel):
    """One vendor device; unavailable metrics remain None instead of zero."""

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
    def validate_memory_capacity(self) -> Self:
        if self.memory_total_bytes is None:
            return self
        if self.memory_used_bytes is not None and self.memory_used_bytes > self.memory_total_bytes:
            raise ValueError("memory_used_bytes cannot exceed memory_total_bytes")
        if self.memory_available_bytes is not None and self.memory_available_bytes > self.memory_total_bytes:
            raise ValueError("memory_available_bytes cannot exceed memory_total_bytes")
        return self


class MachineInfo(_MachineModel):
    """One resource snapshot and the identity of the running AxonX build."""

    axonx: BuildInfo
    cpu: CpuInfo
    memory: MemoryInfo
    gpus: list[GpuInfo] = Field(default_factory=list)


class PythonRuntimeInfo(_MachineModel):
    """The interpreter serving machine operations."""

    version: str
    executable: str


class DiskInfo(_MachineModel):
    """Disk capacity at the workspace's nearest existing ancestor."""

    path: str
    total_bytes: int = Field(ge=0)
    used_bytes: int = Field(ge=0)
    free_bytes: int = Field(ge=0)


class WorkspaceDiagnostics(_MachineModel):
    """Workspace existence and disk capacity without creating directories."""

    path: str
    exists: bool
    disk: DiskInfo


class MachineDiagnostics(MachineInfo):
    """A resource snapshot extended with runtime and configuration checks."""

    python: PythonRuntimeInfo
    platform: str
    cwd: str
    workspace: WorkspaceDiagnostics
    credentials_configured: dict[str, bool]
    service_auth_enabled: bool


class MachineHealth(_MachineModel):
    """Reachability of one configured target service."""

    address: str = Field(min_length=1)
    healthy: bool


class PythonOutput(_MachineModel):
    """Bounded child output; a timeout has no normal exit code."""

    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = 0
    stdout_truncated: bool = False
    stderr_truncated: bool = False
