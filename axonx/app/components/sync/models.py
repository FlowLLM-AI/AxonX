"""Source-owned display plans, publication versions and push results."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from os import stat_result
from pathlib import Path

from ....client.config import archived_bytes


class SnapshotChangedError(OSError):
    """A source changed while its display replica was being prepared."""


class ReplicaBudgetError(ValueError):
    """A replica cannot fit the transfer budget after sampling and omissions."""


@dataclass(frozen=True, slots=True)
class TaskFile:
    path: Path
    relative: str
    size: int
    modified_ns: int
    inode: int
    revision: str

    @classmethod
    def capture(cls, path: Path, relative: str, revision: str = "") -> "TaskFile":
        stat = path.stat()
        return cls(
            path,
            relative,
            stat.st_size,
            stat.st_mtime_ns,
            stat.st_ino,
            revision or f"{stat.st_size}:{stat.st_mtime_ns}",
        )

    def matches(self, stat: stat_result) -> bool:
        return (self.size, self.modified_ns, self.inode) == (stat.st_size, stat.st_mtime_ns, stat.st_ino)

    @property
    def archived_bytes(self) -> int:
        return archived_bytes(self.size)


@dataclass(frozen=True, slots=True)
class TaskPlan:
    """Complete sender files and their reserved archive size."""

    directory: Path
    files: tuple[TaskFile, ...]
    size: int
    omitted: dict[str, str] = field(default_factory=dict)

    @classmethod
    def capture(
        cls,
        directory: Path,
        names: Iterable[str],
        *,
        omitted: dict[str, str] | None = None,
        revisions: Mapping[str, str] | None = None,
    ) -> "TaskPlan":
        files = tuple(
            TaskFile.capture(directory / name, name, (revisions or {}).get(name, "")) for name in sorted(names)
        )
        return cls(directory, files, sum(item.archived_bytes for item in files), dict(omitted or {}))


@dataclass(slots=True)
class SyncReport:
    uploaded: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)
    deferred: list[str] = field(default_factory=list)
    archives: int = 0
