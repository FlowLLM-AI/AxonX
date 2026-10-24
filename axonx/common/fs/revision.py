"""File revisions without reading payload bytes."""

from pathlib import Path


def file_revision(path: Path) -> str:
    """Return size and nanosecond mtime; this is not a content checksum."""
    stat = Path(path).stat()
    return f"{stat.st_size}:{stat.st_mtime_ns}"
