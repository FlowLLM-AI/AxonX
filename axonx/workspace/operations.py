"""Delete validated workspace entries."""

import shutil
from pathlib import Path

from .paths import resolve_deletable_path


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
