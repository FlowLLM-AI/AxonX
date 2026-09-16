"""List and delete validated workspace entries."""

import logging
import shutil
from pathlib import Path
from typing import Any

from .paths import resolve_deletable_path, resolve_workspace_path
from .preview import preview_kind

MAX_DIRECTORY_ENTRIES = 5_000
logger = logging.getLogger(__name__)


def list_entries(root: Path, relative_path: str, require_metadata: bool = False) -> dict[str, Any]:
    directory = resolve_workspace_path(root, relative_path)
    if not directory.exists():
        raise ValueError("Workspace directory does not exist")
    if not directory.is_dir():
        raise ValueError("Workspace path is not a directory")

    entries: list[dict[str, Any]] = []
    children = sorted(directory.iterdir(), key=lambda item: item.name.casefold())
    truncated = len(children) > MAX_DIRECTORY_ENTRIES
    for child in children[:MAX_DIRECTORY_ENTRIES]:
        if require_metadata and child.is_dir() and not (child / "metadata.json").is_file():
            logger.warning("Skipping task directory without metadata.json: %s", child)
            continue
        relative = child.relative_to(root).as_posix()
        try:
            stat = child.lstat() if child.is_symlink() else child.stat()
        except (OSError, RuntimeError):
            stat = child.lstat()

        if child.is_symlink():
            kind = "symlink"
        elif child.is_dir():
            kind = "directory"
        else:
            kind = "file"
        supported_kind = preview_kind(child) if kind == "file" else None
        entries.append(
            {
                "name": child.name,
                "path": relative,
                "kind": kind,
                "preview_kind": supported_kind,
                "supported": supported_kind is not None,
                "size": stat.st_size if kind == "file" else None,
                "modified_at": stat.st_mtime,
            },
        )
    entries.sort(key=lambda entry: (entry["kind"] != "directory", entry["name"].casefold()))
    return {"path": relative_path, "entries": entries, "truncated": truncated}


def delete_entry(root: Path, relative_path: str) -> dict[str, str]:
    target = resolve_deletable_path(root, relative_path)
    if not target.exists():
        raise ValueError("Workspace entry does not exist")
    if target.is_dir():
        shutil.rmtree(target)
        kind = "directory"
    elif target.is_file():
        target.unlink()
        kind = "file"
    else:
        raise ValueError("Workspace entry is not a regular file or directory")
    return {"deleted": relative_path, "kind": kind}


def delete_entries(root: Path, relative_paths: list[str]) -> dict[str, list[dict[str, str]]]:
    """Validate a batch first, then delete unique top-level selections."""
    if not relative_paths:
        raise ValueError("At least one workspace entry is required")
    if len(relative_paths) > 200:
        raise ValueError("At most 200 workspace entries can be deleted at once")

    normalized: list[str] = []
    for relative_path in dict.fromkeys(relative_paths):
        if not isinstance(relative_path, str) or not relative_path:
            raise ValueError("Workspace paths must be non-empty strings")
        target = resolve_deletable_path(root, relative_path)
        if not target.exists() or not (target.is_file() or target.is_dir()):
            raise ValueError(f"Workspace entry does not exist: {relative_path}")
        normalized.append(target.relative_to(root).as_posix())

    selected = set(normalized)
    roots = [
        path
        for path in normalized
        if not any(parent.as_posix() in selected for parent in Path(path).parents if parent.as_posix() != ".")
    ]
    deleted = [delete_entry(root, path) for path in roots]
    return {"deleted": deleted}
