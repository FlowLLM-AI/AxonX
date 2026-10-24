"""Upload naming and staging policy inside the application workspace."""

from pathlib import Path
from ...common.fs.paths import ConfinedPaths

COPY_DIR = "tmp"
MAX_FILENAME_LENGTH = 200


class WorkspacePaths(ConfinedPaths):
    """Extend path confinement with the application's upload directory policy."""

    def __init__(self, workspace_path: Path, copy_dir: str = COPY_DIR):
        super().__init__(workspace_path)
        configured_copy_dir = self._copy_dir_option(copy_dir)
        self.copy_root = self.resolve(configured_copy_dir)
        self.copy_dir = self.relative(self.copy_root) or "."

    @staticmethod
    def _copy_dir_option(copy_dir: str) -> str:
        """Validate the configured copy directory and return it in relative form."""
        if not isinstance(copy_dir, str) or not copy_dir.strip():
            raise ValueError("copy_dir must be a non-empty workspace-relative path")
        candidate = Path(copy_dir)
        if candidate.is_absolute():
            raise ValueError("copy_dir must be relative to the workspace")
        if any(part == ".." for part in candidate.parts):
            raise ValueError("copy_dir cannot contain parent traversal")
        return copy_dir.strip().rstrip("/") or "."

    def copy_name(self, filename: str) -> str:
        """Accept one plain file name, rejecting separators and traversal."""
        if not isinstance(filename, str) or not filename.strip():
            raise ValueError("Upload filename must be a non-empty string")
        if Path(filename).name != filename or filename in {".", ".."}:
            raise ValueError(f"Invalid upload filename: {filename!r}")
        if "\x00" in filename:
            raise ValueError("Upload filename cannot contain a NUL byte")
        if len(filename) > MAX_FILENAME_LENGTH:
            raise ValueError(f"Upload filename exceeds {MAX_FILENAME_LENGTH} characters")
        return filename

    def copy_directory(self, directory: str | None) -> Path:
        """Resolve the directory that receives an uploaded file.

        The copy directory itself is a valid destination, so that configuring it as
        the workspace root stages uploads beside everything else.
        """
        relative = self.copy_dir if directory is None else directory
        if not isinstance(relative, str) or not relative.strip():
            raise ValueError("Upload directory must be a non-empty workspace-relative path")
        target = self.resolve(relative)
        if not target.is_relative_to(self.copy_root):
            raise ValueError(f"Uploads are confined to the workspace {self.copy_dir!r} directory")
        return target

    def staged(self, relative_path: str) -> Path:
        """Resolve one file inside the copy directory, which need not exist yet.

        A copy that a consumer already moved elsewhere is gone rather than missing,
        so existence is left to the caller that needs the bytes. The copy directory
        itself is refused: it is a tree, not a copy.
        """
        if not isinstance(relative_path, str) or not relative_path.strip():
            raise ValueError("Staged path must be a non-empty workspace-relative path")
        target = self.resolve(relative_path)
        if target == self.copy_root or not target.is_relative_to(self.copy_root):
            raise ValueError(f"Staged files are confined to the workspace {self.copy_dir!r} directory")
        if (self.root / relative_path).is_symlink():
            raise ValueError(f"Staged paths cannot be symlinks: {relative_path}")
        return target
