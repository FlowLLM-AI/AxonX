"""Bounded, path-safe workspace listing and deletion."""

import heapq
import shutil
from collections.abc import Callable, Iterable
from pathlib import Path, PurePosixPath

from .models import DeletedEntry, WorkspaceEntry, WorkspaceListing
from .paths import WorkspacePaths
from .preview import preview_kind

MAX_DIRECTORY_ENTRIES = 5_000
MAX_DELETE_ENTRIES = 200
EntryFilter = Callable[[Path, WorkspaceEntry], bool]


def list_workspace_entries(
    workspace_path: Path,
    path: str = "",
    *,
    include: EntryFilter | None = None,
) -> WorkspaceListing:
    """Return a bounded, directory-first listing without materialising the tree."""
    paths = WorkspacePaths(workspace_path)
    directory = paths.resolve_directory(path)
    entries = _iter_entries(paths, directory, include)
    selected = heapq.nsmallest(
        MAX_DIRECTORY_ENTRIES + 1,
        entries,
        key=_entry_sort_key,
    )
    return WorkspaceListing(
        path=paths.relative(directory),
        entries=selected[:MAX_DIRECTORY_ENTRIES],
        truncated=len(selected) > MAX_DIRECTORY_ENTRIES,
    )


def delete_workspace_entries(
    workspace_path: Path, requested_paths: list[str]
) -> list[DeletedEntry]:
    """Validate the whole selection, then delete only its top-level roots."""
    if not requested_paths:
        raise ValueError("At least one workspace entry is required")
    if len(requested_paths) > MAX_DELETE_ENTRIES:
        raise ValueError(
            f"At most {MAX_DELETE_ENTRIES} workspace entries can be deleted at once"
        )

    paths = WorkspacePaths(workspace_path)
    selected: list[str] = []
    for relative_path in dict.fromkeys(requested_paths):
        if not isinstance(relative_path, str) or not relative_path:
            raise ValueError("Workspace paths must be non-empty strings")
        target = paths.resolve_deletable(relative_path)
        if not target.exists() or not (target.is_file() or target.is_dir()):
            raise ValueError(f"Workspace entry does not exist: {relative_path}")
        selected.append(paths.relative(target))

    names = set(selected)
    roots = [
        path
        for path in selected
        if not any(str(parent) in names for parent in PurePosixPath(path).parents)
    ]
    return [_delete_entry(paths, path) for path in roots]


def _iter_entries(
    paths: WorkspacePaths,
    directory: Path,
    include: EntryFilter | None,
) -> Iterable[WorkspaceEntry]:
    for child in directory.iterdir():
        entry = _entry(paths, child)
        if entry is not None and (include is None or include(child, entry)):
            yield entry


def _entry(paths: WorkspacePaths, child: Path) -> WorkspaceEntry | None:
    try:
        if child.is_symlink():
            kind = "symlink"
            stat = child.lstat()
        elif child.is_dir():
            kind = "directory"
            stat = child.stat()
        else:
            kind = "file"
            stat = child.stat()
    except (OSError, RuntimeError):
        return None
    preview = preview_kind(child) if kind == "file" else None
    return WorkspaceEntry(
        name=child.name,
        path=paths.relative(child),
        kind=kind,
        preview_kind=preview,
        supported=preview is not None,
        size=stat.st_size if kind == "file" else None,
        modified_at=stat.st_mtime,
    )


def _entry_sort_key(entry: WorkspaceEntry) -> tuple[bool, str, str]:
    return entry.kind != "directory", entry.name.casefold(), entry.name


def _delete_entry(paths: WorkspacePaths, relative_path: str) -> DeletedEntry:
    target = paths.resolve_deletable(relative_path)
    if target.is_dir():
        shutil.rmtree(target)
        kind = "directory"
    elif target.is_file():
        target.unlink()
        kind = "file"
    else:
        raise ValueError("Workspace entry is not a regular file or directory")
    return DeletedEntry(deleted=relative_path, kind=kind)
