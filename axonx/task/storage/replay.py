"""Publish and verify portable replay manifests and their file snapshots."""

import hashlib
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ..models.artifacts import ArtifactRecord, ReplayEvent, ReplayManifest, ReplaySource
from .files import atomic_write_json, file_revision, snapshot_file


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

    def file(self, record: ArtifactRecord) -> Path:
        path = (self.root / record.path).resolve(strict=True)
        if Path(record.path).is_absolute() or not path.is_relative_to(self.root):
            raise ValueError("Replay file escapes stream directory")
        if not path.is_file() or path.stat().st_size != record.size or file_revision(path) != record.revision:
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
                snapshot_file(source, target, isolated=True)
                return ArtifactRecord(
                    path=target.relative_to(root).as_posix(),
                    revision=file_revision(target),
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
