"""Immutable values exchanged by Task synchronization code."""

from dataclasses import dataclass, field
from pathlib import Path

TAR_BLOCK_BYTES = 512


@dataclass(frozen=True, slots=True)
class TaskFile:
    path: Path
    relative: str
    size: int
    modified_ns: int
    inode: int

    @property
    def archived_bytes(self) -> int:
        blocks = (self.size + TAR_BLOCK_BYTES - 1) // TAR_BLOCK_BYTES
        return TAR_BLOCK_BYTES + blocks * TAR_BLOCK_BYTES


@dataclass(frozen=True, slots=True)
class TaskPlan:
    files: tuple[TaskFile, ...]
    rejected: tuple[str, ...]
    size: int

    @property
    def empty(self) -> bool:
        return not self.files and not self.rejected

    @property
    def transferable(self) -> bool:
        return bool(self.files) and not self.rejected


@dataclass(frozen=True, slots=True)
class SyncReport:
    uploaded: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
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
