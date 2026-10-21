"""File revisions without reading payload bytes."""

from collections.abc import Iterable
from pathlib import Path


def file_revision(path: Path) -> str:
    """Return size and nanosecond mtime; this is not a content checksum."""
    stat = Path(path).stat()
    return f"{stat.st_size}:{stat.st_mtime_ns}"


def file_versions(paths: Iterable[Path], *, budget=None, report=None) -> dict[Path, str]:
    """Read metadata for explicit inputs, honoring the caller's budget."""
    if budget is not None:
        budget.check()
    paths = sorted(set(map(Path, paths)))
    versions = {}
    for index, path in enumerate(paths, 1):
        if budget is not None:
            budget.check()
        versions[path] = file_revision(path)
        if report is not None and (index % 250 == 0 or index == len(paths)):
            report(
                name="raw_inputs",
                completed=index,
                total=len(paths),
                unit="files",
                state="done" if index == len(paths) else "running",
            )
    return versions
