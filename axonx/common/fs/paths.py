"""Root-confined filesystem paths without upload or Task policies."""

from pathlib import Path


class ConfinedPaths:
    """Resolve relative paths below one root, refusing traversal and symlinks."""

    def __init__(self, root: Path):
        self.root = Path(root).expanduser().resolve()

    def resolve(self, relative_path: str) -> Path:
        """Resolve one workspace-relative path, refusing anything that leaves it.

        Every path segment is checked so symlinks cannot redirect the operation.
        """
        if not isinstance(relative_path, str):
            raise TypeError("Workspace path must be a string")
        candidate = Path(relative_path)
        if candidate.is_absolute():
            raise ValueError("Workspace path must be relative")
        if any(part == ".." for part in candidate.parts):
            raise ValueError("Workspace path cannot contain parent traversal")
        unresolved = self.root / candidate
        current = self.root
        for part in candidate.parts:
            current /= part
            if current.is_symlink():
                raise ValueError("Workspace paths cannot traverse symlinks")
        target = unresolved.resolve()
        if not target.is_relative_to(self.root):
            raise ValueError("Workspace path is outside the configured workspace")
        return target

    def resolve_file(self, relative_path: str) -> Path:
        """Resolve one workspace file that must already exist."""
        target = self.resolve(relative_path)
        if not target.exists():
            raise ValueError("Workspace file does not exist")
        if not target.is_file():
            raise ValueError("Workspace path is not a file")
        return target

    def resolve_directory(self, relative_path: str) -> Path:
        """Resolve one workspace directory that must already exist."""
        target = self.resolve(relative_path)
        if not target.exists():
            raise ValueError("Workspace directory does not exist")
        if not target.is_dir():
            raise ValueError("Workspace path is not a directory")
        return target

    def resolve_deletable(self, relative_path: str) -> Path:
        """Resolve one deletable entry, also refusing the root itself."""
        if not isinstance(relative_path, str) or not relative_path.strip():
            raise ValueError("The workspace root cannot be deleted")
        target = self.resolve(relative_path)
        if target == self.root:
            raise ValueError("The workspace root cannot be deleted")
        return target

    def relative(self, path: Path) -> str:
        """Return one resolved path in workspace-relative form."""
        relative = path.relative_to(self.root).as_posix()
        return "" if relative == "." else relative
