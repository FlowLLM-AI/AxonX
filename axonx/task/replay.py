"""Portable, hash-verified event files and a synchronous replay driver."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
from pathlib import Path
import shutil
import tempfile
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from ..utils.fs import atomic_write_json, file_sha256
from .schemas.artifact import ArtifactRecord
from .core.clock import ReplayClock


class ReplayFile(ArtifactRecord):
    """Use the framework's shared relative-path, size and digest contract."""


class ReplayEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    key: str = Field(min_length=1)
    available_at: AwareDatetime
    files: dict[str, ReplayFile]
    attributes: dict[str, Any] = Field(default_factory=dict)


class ReplayManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    version: Literal[1] = 1
    kind: Literal["event_stream"] = "event_stream"
    events: list[ReplayEvent] = Field(min_length=1)
    context: dict[str, ReplayFile] = Field(default_factory=dict)
    attributes: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def ordered(self):
        times = [event.available_at for event in self.events]
        if times != sorted(times):
            raise ValueError("Replay events must be ordered by availability")
        return self


@dataclass(frozen=True)
class ReplaySource:
    """An event to snapshot; paths are never retained as live payload references."""

    key: str
    available_at: datetime
    files: dict[str, Path]
    attributes: dict[str, Any] = field(default_factory=dict)


class ReplayStream:
    """Own a portable manifest and copied files; opening verifies every payload."""

    def __init__(self, directory: Path):
        self.root = Path(directory).resolve(strict=True)
        content = (self.root / "stream.json").read_bytes()
        self.manifest_sha256 = hashlib.sha256(content).hexdigest()
        self.manifest = ReplayManifest.model_validate_json(content)
        for record in self.manifest.context.values():
            self.file(record)
        for event in self.manifest.events:
            for record in event.files.values():
                self.file(record)

    def file(self, record: ReplayFile) -> Path:
        path = (self.root / record.path).resolve(strict=True)
        if Path(record.path).is_absolute() or not path.is_relative_to(self.root):
            raise ValueError("Replay file escapes stream directory")
        if not path.is_file() or path.stat().st_size != record.size or file_sha256(path) != record.sha256:
            raise ValueError(f"Replay file changed: {record.path}")
        return path

    @classmethod
    def create(
        cls,
        directory: Path,
        events: Iterable[ReplaySource],
        *,
        context: dict[str, Path] | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> "ReplayStream":
        """Publish a new dataset atomically; never overwrite an existing dataset."""
        directory = Path(directory).absolute()
        if directory.exists():
            raise FileExistsError(directory)
        directory.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".replay-", dir=directory.parent) as temporary:
            root = Path(temporary) / "stream"
            (root / "files").mkdir(parents=True)
            counter = 0

            def copy(source):
                nonlocal counter
                counter += 1
                target = root / "files" / f"{counter:06d}{Path(source).suffix}"
                shutil.copyfile(source, target)
                return ReplayFile(
                    path=target.relative_to(root).as_posix(),
                    sha256=file_sha256(target),
                    size=target.stat().st_size,
                )

            records = [
                ReplayEvent(
                    key=event.key,
                    available_at=event.available_at,
                    files={name: copy(source) for name, source in event.files.items()},
                    attributes=event.attributes,
                )
                for event in events
            ]
            manifest = ReplayManifest(
                events=sorted(records, key=lambda event: event.available_at),
                context={name: copy(source) for name, source in (context or {}).items()},
                attributes=attributes or {},
            )
            atomic_write_json(root / "stream.json", manifest.model_dump(mode="json"))
            root.rename(directory)
        return cls(directory)


class ReplayCursor:
    """Deliver events only when available and strictly before the caller's deadline."""

    def __init__(self, stream: ReplayStream, clock: ReplayClock):
        self.stream, self.clock, self.position = stream, clock, 0

    def wait(
        self,
        deadline: datetime,
        consume: Callable[[ReplayEvent], None],
        ready: Callable[[], bool],
    ) -> bool:
        while self.clock.now() < deadline:
            if ready():
                return True
            if self.position == len(self.stream.manifest.events):
                break
            event = self.stream.manifest.events[self.position]
            if event.available_at >= deadline:
                break
            self.clock.advance_to(max(self.clock.now(), event.available_at))
            consume(event)
            self.position += 1
        if self.clock.now() < deadline:
            self.clock.advance_to(deadline)
        return False
