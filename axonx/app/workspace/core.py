"""Application-owned workspace browsing, preview and upload staging."""

from __future__ import annotations

import heapq
import shutil
from collections.abc import Callable, Iterable
from pathlib import Path, PurePosixPath

from .models import DeletedEntry, FilePreview, WorkspaceEntry, WorkspaceListing
from .preview import PREVIEW_ROWS, preview_file, preview_kind
from .uploads import DEFAULT_UPLOAD_RETENTION_DAYS, UploadStore

MAX_DIRECTORY_ENTRIES = 5_000
MAX_DELETE_ENTRIES = 200
EntryFilter = Callable[[Path, WorkspaceEntry], bool]


class Workspace:
    """Own a normalized root and reusable, bounded file operations.

    Construction never creates files. Operations return validated workspace models.
    A transfer budget of None leaves byte limits to the caller.
    Uploads expire files older than upload_retention_days on each new upload.
    """

    def __init__(
        self,
        root: str | Path,
        *,
        copy_dir: str = "tmp/uploads",
        transfer_budget_bytes: int | None = None,
        upload_retention_days: int = DEFAULT_UPLOAD_RETENTION_DAYS,
    ) -> None:
        self.root = Path(root).expanduser().resolve()
        self.uploads = UploadStore(self, copy_dir, transfer_budget_bytes, retention_days=upload_retention_days)

    def ensure(self) -> Path:
        """Create the workspace root only when explicitly requested."""
        self.root.mkdir(parents=True, exist_ok=True)
        return self.root

    def locate(self, path: str | Path, *, external: bool = False) -> Path:
        """Resolve a configured path or Task input, allowing absolute paths.

        Symlinks are resolved. External research inputs require explicit opt-in;
        use resolve() for untrusted workspace-relative file operations instead.
        """
        candidate = Path(path).expanduser()
        target = (candidate if candidate.is_absolute() else self.root / candidate).resolve()
        if not external and not target.is_relative_to(self.root):
            raise ValueError("Workspace path is outside the configured workspace")
        return target

    def resolve(self, relative_path: str) -> Path:
        """Resolve a relative path, refusing traversal and every symlink segment."""
        if not isinstance(relative_path, str):
            raise TypeError("Workspace path must be a string")
        candidate = Path(relative_path)
        if candidate.is_absolute():
            raise ValueError("Workspace path must be relative")
        if any(part == ".." for part in candidate.parts):
            raise ValueError("Workspace path cannot contain parent traversal")
        current = self.root
        for part in candidate.parts:
            current /= part
            if current.is_symlink():
                raise ValueError("Workspace paths cannot traverse symlinks")
        target = (self.root / candidate).resolve()
        if not target.is_relative_to(self.root):
            raise ValueError("Workspace path is outside the configured workspace")
        return target

    def resolve_file(self, relative_path: str) -> Path:
        target = self.resolve(relative_path)
        if not target.exists():
            raise ValueError("Workspace file does not exist")
        if not target.is_file():
            raise ValueError("Workspace path is not a file")
        return target

    def resolve_directory(self, relative_path: str) -> Path:
        target = self.resolve(relative_path)
        if not target.exists():
            raise ValueError("Workspace directory does not exist")
        if not target.is_dir():
            raise ValueError("Workspace path is not a directory")
        return target

    def resolve_deletable(self, relative_path: str) -> Path:
        if not isinstance(relative_path, str) or not relative_path.strip():
            raise ValueError("The workspace root cannot be deleted")
        target = self.resolve(relative_path)
        if target == self.root:
            raise ValueError("The workspace root cannot be deleted")
        return target

    def relative(self, path: Path) -> str:
        relative = path.relative_to(self.root).as_posix()
        return "" if relative == "." else relative

    def list_entries(self, path: str = "", *, include: EntryFilter | None = None, offset: int = 0) -> WorkspaceListing:
        """Return a directory-first page, filtering before applying the limit."""
        if offset < 0:
            raise ValueError("Directory offset must be non-negative")
        directory = self.resolve_directory(path)
        selected = heapq.nsmallest(
            offset + MAX_DIRECTORY_ENTRIES + 1,
            self._entries(directory, include),
            key=lambda entry: (entry.kind != "directory", entry.name.casefold(), entry.name),
        )
        return WorkspaceListing(
            path=self.relative(directory),
            workspace_root=str(self.root),
            entries=selected[offset : offset + MAX_DIRECTORY_ENTRIES],
            truncated=len(selected) > offset + MAX_DIRECTORY_ENTRIES,
        )

    def _entries(self, directory: Path, include: EntryFilter | None) -> Iterable[WorkspaceEntry]:
        for child in directory.iterdir():
            try:
                if child.is_symlink():
                    kind, stat = "symlink", child.lstat()
                elif child.is_dir():
                    kind, stat = "directory", child.stat()
                else:
                    kind, stat = "file", child.stat()
            except (OSError, RuntimeError):
                continue
            preview = preview_kind(child) if kind == "file" else None
            entry = WorkspaceEntry(
                name=child.name,
                path=self.relative(child),
                kind=kind,
                preview_kind=preview,
                supported=preview is not None,
                size=stat.st_size if kind == "file" else None,
                modified_at=stat.st_mtime,
            )
            if include is None or include(child, entry):
                yield entry

    def preview_file(
        self, path: str, offset: int = 0, limit: int = PREVIEW_ROWS, *, max_bytes: int | None = None
    ) -> FilePreview:
        """Read a bounded preview, loading format libraries on demand."""
        return preview_file(self, path, offset, limit, max_bytes=max_bytes)

    def delete_entries(self, requested_paths: list[str]) -> list[DeletedEntry]:
        """Validate the complete selection before deleting its top-level roots."""
        if not requested_paths:
            raise ValueError("At least one workspace entry is required")
        if len(requested_paths) > MAX_DELETE_ENTRIES:
            raise ValueError(f"At most {MAX_DELETE_ENTRIES} workspace entries can be deleted at once")
        selected = []
        for relative_path in dict.fromkeys(requested_paths):
            if not isinstance(relative_path, str) or not relative_path:
                raise ValueError("Workspace paths must be non-empty strings")
            target = self.resolve_deletable(relative_path)
            if not target.exists() or not (target.is_file() or target.is_dir()):
                raise ValueError(f"Workspace entry does not exist: {relative_path}")
            selected.append(self.relative(target))
        names = set(selected)
        roots = [path for path in selected if not any(str(parent) in names for parent in PurePosixPath(path).parents)]
        deleted = []
        for path in roots:
            target = self.resolve_deletable(path)
            if target.is_dir():
                shutil.rmtree(target)
                kind = "directory"
            elif target.is_file():
                target.unlink()
                kind = "file"
            else:
                raise ValueError("Workspace entry is not a regular file or directory")
            deleted.append(DeletedEntry(deleted=path, kind=kind))
        return deleted
