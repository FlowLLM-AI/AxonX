"""Describe published artifacts and verify their owned paths and file revisions."""

import stat
from pathlib import Path

from ..models.artifacts import ArtifactRecord
from .workspace import resolve_relative_path


def verify_artifact(root: Path, record: ArtifactRecord) -> Path:
    """Require a regular payload matching its recorded size and revision."""
    path = resolve_relative_path(root, record.path)
    info = path.stat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_size != record.size
        or f"{info.st_size}:{info.st_mtime_ns}" != record.revision
    ):
        raise ValueError(f"Artifact revision mismatch: {record.path}")
    return path


def artifact_record(path: Path, root: Path) -> dict:
    """Describe a published file using one consistent filesystem observation."""
    info = path.stat()
    return ArtifactRecord(
        path=path.relative_to(root).as_posix(),
        size=info.st_size,
        revision=f"{info.st_size}:{info.st_mtime_ns}",
    ).model_dump()
