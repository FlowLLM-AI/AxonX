"""Application-owned workspace browsing, preview and upload staging."""

from __future__ import annotations

import heapq
import os
import shutil
import tempfile
from collections.abc import AsyncIterator, Callable, Iterable
from contextlib import suppress
from pathlib import Path, PurePosixPath
from uuid import uuid4

from ...client.models import StagedFile
from ...utils.async_work import run_blocking
from .models import DeletedEntry, FilePreview, WorkspaceEntry, WorkspaceListing
from .preview import PREVIEW_ROWS, preview_file, preview_kind

MAX_DIRECTORY_ENTRIES = 5_000
MAX_DELETE_ENTRIES = 200
MAX_FILENAME_LENGTH = 200
EntryFilter = Callable[[Path, WorkspaceEntry], bool]


class Workspace:
    """Own a normalized root and reusable, bounded file operations.

    Construction never creates files. Operations return validated workspace models.
    A transfer budget of None leaves byte limits to the caller.
    """

    def __init__(
        self,
        root: str | Path,
        *,
        copy_dir: str = "tmp",
        transfer_budget_bytes: int | None = None,
    ) -> None:
        if transfer_budget_bytes is not None and transfer_budget_bytes <= 0:
            raise ValueError("transfer_budget_bytes must be positive")
        self.root = Path(root).expanduser().resolve()
        self.copy_dir = self._copy_dir_option(copy_dir)
        self.transfer_budget_bytes = transfer_budget_bytes

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

    @staticmethod
    def _copy_dir_option(copy_dir: str) -> str:
        if not isinstance(copy_dir, str) or not copy_dir.strip():
            raise ValueError("copy_dir must be a non-empty workspace-relative path")
        candidate = Path(copy_dir)
        if candidate.is_absolute():
            raise ValueError("copy_dir must be relative to the workspace")
        if any(part == ".." for part in candidate.parts):
            raise ValueError("copy_dir cannot contain parent traversal")
        return copy_dir.strip().rstrip("/") or "."

    @property
    def copy_root(self) -> Path:
        return self.resolve(self.copy_dir)

    @staticmethod
    def _copy_name(filename: str) -> str:
        if not isinstance(filename, str) or not filename.strip():
            raise ValueError("Upload filename must be a non-empty string")
        if Path(filename).name != filename or filename in {".", ".."}:
            raise ValueError(f"Invalid upload filename: {filename!r}")
        if "\x00" in filename:
            raise ValueError("Upload filename cannot contain a NUL byte")
        if len(filename) > MAX_FILENAME_LENGTH:
            raise ValueError(f"Upload filename exceeds {MAX_FILENAME_LENGTH} characters")
        return filename

    def _copy_directory(self, directory: str | None) -> Path:
        relative = self.copy_dir if directory is None else directory
        if not isinstance(relative, str) or not relative.strip():
            raise ValueError("Upload directory must be a non-empty workspace-relative path")
        target = self.resolve(relative)
        if not target.is_relative_to(self.copy_root):
            raise ValueError(f"Uploads are confined to the workspace {self.copy_dir!r} directory")
        return target

    def _staged(self, relative_path: str) -> Path:
        if not isinstance(relative_path, str) or not relative_path.strip():
            raise ValueError("Staged path must be a non-empty workspace-relative path")
        target = self.resolve(relative_path)
        if target == self.copy_root or not target.is_relative_to(self.copy_root):
            raise ValueError(f"Staged files are confined to the workspace {self.copy_dir!r} directory")
        return target

    def staged_file(self, relative_path: str) -> Path:
        target = self._staged(relative_path)
        if not target.is_file():
            raise ValueError("Staged file does not exist")
        return target

    def stage_bytes(self, data: bytes, filename: str, directory: str | None = None) -> StagedFile:
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("Uploaded content must be bytes")
        self._check_size(len(data))
        target = self._target(self._copy_directory(directory), self._copy_name(filename))
        try:
            descriptor, temporary = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.")
            os.close(descriptor)
            try:
                Path(temporary).write_bytes(bytes(data))
                os.replace(temporary, target)
            finally:
                Path(temporary).unlink(missing_ok=True)
        except BaseException:
            target.parent.rmdir()
            raise
        return self._report(target, len(data))

    async def stage_stream(
        self, chunks: AsyncIterator[bytes], filename: str, directory: str | None = None, size: int | None = None
    ) -> StagedFile:
        """Publish a complete stream atomically; remove partial files on failure."""
        if size is not None:
            if size < 0:
                raise ValueError("Declared upload size must not be negative")
            self._check_size(size)
        name = self._copy_name(filename)
        target_dir = self._copy_directory(directory)
        existed = target_dir.is_dir()
        target_dir.mkdir(parents=True, exist_ok=True)
        written = 0
        descriptor, temporary = tempfile.mkstemp(dir=target_dir, prefix=f".{name}.", suffix=".tmp")
        pending: Path | None = Path(temporary)
        target: Path | None = None
        try:
            with os.fdopen(descriptor, "wb") as handle:
                async for chunk in chunks:
                    if not isinstance(chunk, (bytes, bytearray)):
                        raise TypeError("Uploaded content must be bytes")
                    written += len(chunk)
                    self._check_size(written)
                    await run_blocking(handle.write, chunk)
            if size is not None and written != size:
                raise ValueError(f"Uploaded content size {written} does not match declared size {size}")
            target = self._target(target_dir, name)
            os.replace(pending, target)
            pending = None
            return self._report(target, written)
        finally:
            if pending is not None:
                pending.unlink(missing_ok=True)
                if target is not None:
                    target.parent.rmdir()
            if not existed:
                with suppress(OSError):
                    target_dir.rmdir()

    def discard_staged(self, relative_path: str) -> str:
        """Remove a staged copy and empty staging directories; cleanup is idempotent."""
        target = self._staged(relative_path)
        if target.is_file():
            target.unlink()
        directory = target.parent
        while directory != self.root and directory.is_relative_to(self.copy_root):
            try:
                directory.rmdir()
            except OSError:
                break
            directory = directory.parent
        return self.relative(target)

    def _check_size(self, size: int) -> None:
        if self.transfer_budget_bytes is not None and size > self.transfer_budget_bytes:
            raise ValueError(f"Upload exceeds the configured budget of {self.transfer_budget_bytes} bytes")

    @staticmethod
    def _target(target_dir: Path, name: str) -> Path:
        target_dir.mkdir(parents=True, exist_ok=True)
        directory = target_dir / uuid4().hex
        directory.mkdir()
        return directory / name

    def _report(self, target: Path, size: int) -> StagedFile:
        return StagedFile(path=self.relative(target), location=str(target), size=size)
