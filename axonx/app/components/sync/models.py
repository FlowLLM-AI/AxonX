"""Internal replica plans and results owned by application synchronization."""

from collections.abc import Iterable
from dataclasses import dataclass, field
from os import stat_result
from pathlib import Path


class SnapshotChangedError(OSError):
    """A source changed while its display replica was being prepared."""


class ReplicaBudgetError(ValueError):
    """A replica cannot fit the transfer budget after sampling and omissions."""


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

    @classmethod
    def capture(cls, path: Path, relative: str) -> "TaskFile":
        stat = path.stat()
        return cls(path, relative, stat.st_size, stat.st_mtime_ns, stat.st_ino)

    def matches(self, stat: stat_result) -> bool:
        return (self.size, self.modified_ns, self.inode) == (stat.st_size, stat.st_mtime_ns, stat.st_ino)

    @property
    def archived_bytes(self) -> int:
        return archived_bytes(self.size)


@dataclass(frozen=True, slots=True)
class TaskPlan:
    """Files to transfer and reserved archive size, including any hydrated delta base."""

    files: tuple[TaskFile, ...]
    size: int
    omitted: dict[str, str] = field(default_factory=dict)

    @classmethod
    def capture(cls, directory: Path, names: Iterable[str], *, omitted: dict[str, str] | None = None) -> "TaskPlan":
        files = tuple(TaskFile.capture(directory / name, name) for name in sorted(names))
        return cls(files, sum(item.archived_bytes for item in files), dict(omitted or {}))


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
