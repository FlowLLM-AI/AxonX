"""Resolve paths within the configured workspace."""

from pathlib import Path


def workspace_root(workspace_dir: str) -> Path:
    return Path(workspace_dir).expanduser().resolve()


def resolve_workspace_path(root: Path, relative_path: str) -> Path:
    if not isinstance(relative_path, str):
        raise TypeError("Workspace path must be a string")
    candidate = Path(relative_path)
    if candidate.is_absolute():
        raise ValueError("Workspace path must be relative")
    target = (root / candidate).resolve()
    if not target.is_relative_to(root):
        raise ValueError("Workspace path is outside the configured workspace")
    return target


def resolve_deletable_path(root: Path, relative_path: str) -> Path:
    if not relative_path:
        raise ValueError("The workspace root cannot be deleted")
    candidate = Path(relative_path)
    if candidate.is_absolute():
        raise ValueError("Workspace path must be relative")
    if (root / candidate).is_symlink():
        raise ValueError("Workspace symlinks cannot be deleted")
    target = resolve_workspace_path(root, relative_path)
    if target == root:
        raise ValueError("The workspace root cannot be deleted")
    return target
