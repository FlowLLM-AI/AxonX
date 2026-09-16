"""List workspace directory entries."""

from pathlib import Path
from typing import Any

from .paths import resolve_workspace_path as _resolve_workspace_path
from .preview import preview_kind

MAX_DIRECTORY_ENTRIES = 5_000


def list_entries(root: Path, relative_path: str) -> dict[str, Any]:
    directory = _resolve_workspace_path(root, relative_path)
    if not directory.exists():
        raise ValueError("Workspace directory does not exist")
    if not directory.is_dir():
        raise ValueError("Workspace path is not a directory")

    entries: list[dict[str, Any]] = []
    children = sorted(directory.iterdir(), key=lambda item: item.name.casefold())
    truncated = len(children) > MAX_DIRECTORY_ENTRIES
    for child in children[:MAX_DIRECTORY_ENTRIES]:
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
