"""File transport contracts, source-owned display plans and synchronization results."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from os import stat_result
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class FileRecord(BaseModel):
    """An opaque sender revision; receivers only interpret its size."""

    model_config = ConfigDict(extra="forbid", strict=True)
    size: int = Field(ge=0)
    revision: str = Field(min_length=1)


class FileGroup(BaseModel):
    """One complete set of owned directories, independent of their contents."""

    model_config = ConfigDict(extra="forbid", strict=True)
    version: str = Field(min_length=1)
    revision: int = Field(gt=0)
    directories: dict[str, dict[str, FileRecord]]

    @classmethod
    def capture(cls, plans: Mapping[str, "TaskPlan"], version: str, revision: int) -> "FileGroup":
        return cls(
            version=version,
            revision=revision,
            directories={
                relative: {item.relative: FileRecord(size=item.size, revision=item.revision) for item in plan.files}
                for relative, plan in plans.items()
            },
        )

    @property
    def size(self) -> int:
        return archived_bytes(len(self.model_dump_json().encode())) + sum(
            archived_bytes(record.size) for files in self.directories.values() for record in files.values()
        )


class FileManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")
    groups: dict[str, FileGroup]


class SnapshotChangedError(OSError):
    """A source changed while its display replica was being prepared."""


class ReplicaBudgetError(ValueError):
    """A replica cannot fit the transfer budget after sampling and omissions."""


MANIFEST_NAME = "sync-manifest.json"
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
        return cls(files, sum(item.archived_bytes for item in files), dict(omitted or {}))


@dataclass(slots=True)
class SyncReport:
    uploaded: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)
    oversized: list[str] = field(default_factory=list)
    deferred: list[str] = field(default_factory=list)
    archives: int = 0


@dataclass(frozen=True, slots=True)
class SyncFilesReport:
    archive: str | None = None
    applied: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    files: int = 0
