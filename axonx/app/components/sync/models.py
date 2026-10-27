"""Internal replica plans and results owned by application synchronization."""

from dataclasses import dataclass, field
from pathlib import Path

TAR_BLOCK_BYTES = 512
TAR_PADDING_BYTES = 10_240


def archived_bytes(size: int) -> int:
    """Reserve a tar header plus the complete padded payload."""
    return TAR_BLOCK_BYTES * (1 + (size + TAR_BLOCK_BYTES - 1) // TAR_BLOCK_BYTES)


@dataclass(frozen=True, slots=True)
class TaskFile:
    path: Path
    relative: str
    size: int
    modified_ns: int
    inode: int

    @property
    def archived_bytes(self) -> int:
        return archived_bytes(self.size)


@dataclass(frozen=True, slots=True)
class TaskPlan:
    """Files to transfer and reserved archive size, including any hydrated delta base."""

    files: tuple[TaskFile, ...]
    size: int
    omitted: dict[str, str] = field(default_factory=dict)

    @property
    def empty(self) -> bool:
        return not self.files


@dataclass(slots=True)
class SyncReport:
    uploaded: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)
    oversized: list[str] = field(default_factory=list)
    deferred: list[str] = field(default_factory=list)
    archives: int = 0


@dataclass(frozen=True, slots=True)
class SyncTasksReport:
    archive: str | None = None
    applied: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    files: int = 0
