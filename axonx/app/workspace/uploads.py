"""Workspace-owned upload staging, atomic publication and opportunistic cleanup."""

from __future__ import annotations

import os
import stat
import tempfile
from collections.abc import AsyncIterator
from contextlib import suppress
from pathlib import Path
from time import time
from typing import TYPE_CHECKING
from uuid import uuid4

from ...client.models import StagedFile
from ...utils.async_work import run_blocking

if TYPE_CHECKING:
    from .core import Workspace

MAX_FILENAME_LENGTH = 200
DEFAULT_UPLOAD_RETENTION_DAYS = 7


class UploadStore:
    """Own staged files beneath one validated workspace-relative directory."""

    def __init__(
        self,
        workspace: Workspace,
        directory: str,
        limit: int | None,
        *,
        retention_days: int = DEFAULT_UPLOAD_RETENTION_DAYS,
    ) -> None:
        if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0):
            raise ValueError("transfer_budget_bytes must be a positive integer")
        if isinstance(retention_days, bool) or not isinstance(retention_days, int) or retention_days <= 0:
            raise ValueError("retention_days must be a positive integer")
        self.workspace = workspace
        self.directory = self._validate_directory(directory)
        self.limit = limit
        self.retention_days = retention_days

    @staticmethod
    def _validate_directory(copy_dir: str) -> str:
        if not isinstance(copy_dir, str) or not copy_dir.strip():
            raise ValueError("copy_dir must be a non-empty workspace-relative path")
        candidate = Path(copy_dir)
        if candidate.is_absolute():
            raise ValueError("copy_dir must be relative to the workspace")
        if any(part == ".." for part in candidate.parts):
            raise ValueError("copy_dir cannot contain parent traversal")
        return copy_dir.strip().rstrip("/") or "."

    @property
    def root(self) -> Path:
        return self.workspace.resolve(self.directory)

    @staticmethod
    def _filename(filename: str) -> str:
        if not isinstance(filename, str) or not filename.strip():
            raise ValueError("Upload filename must be a non-empty string")
        if Path(filename).name != filename or filename in {".", ".."}:
            raise ValueError(f"Invalid upload filename: {filename!r}")
        if "\x00" in filename:
            raise ValueError("Upload filename cannot contain a NUL byte")
        if len(filename) > MAX_FILENAME_LENGTH:
            raise ValueError(f"Upload filename exceeds {MAX_FILENAME_LENGTH} characters")
        return filename

    def _directory(self, directory: str | None) -> Path:
        relative = self.directory if directory is None else directory
        if not isinstance(relative, str) or not relative.strip():
            raise ValueError("Upload directory must be a non-empty workspace-relative path")
        target = self.workspace.resolve(relative)
        if not target.is_relative_to(self.root):
            raise ValueError(f"Uploads are confined to the workspace {self.directory!r} directory")
        return target

    def _staged(self, relative_path: str) -> Path:
        if not isinstance(relative_path, str) or not relative_path.strip():
            raise ValueError("Staged path must be a non-empty workspace-relative path")
        target = self.workspace.resolve(relative_path)
        if target == self.root or not target.is_relative_to(self.root):
            raise ValueError(f"Staged files are confined to the workspace {self.directory!r} directory")
        return target

    def file(self, relative_path: str) -> Path:
        target = self._staged(relative_path)
        if not target.is_file():
            raise ValueError("Staged file does not exist")
        return target

    def stage_bytes(self, data: bytes, filename: str, directory: str | None = None) -> StagedFile:
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("Uploaded content must be bytes")
        self._check_size(len(data))
        target_dir = self._directory(directory)
        name = self._filename(filename)
        self.cleanup_expired()
        target = self._target(target_dir, name)
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
        name = self._filename(filename)
        target_dir = self._directory(directory)
        await run_blocking(self.cleanup_expired)
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

    def cleanup_expired(self) -> None:
        """Best-effort removal of files older than retention_days, triggered by uploads."""
        cutoff = time() - self.retention_days * 24 * 60 * 60
        try:
            root = self.root
        except (OSError, ValueError):
            return
        for directory, _, filenames in os.walk(root, topdown=False, followlinks=False):
            for filename in filenames:
                path = Path(directory) / filename
                try:
                    info = path.lstat()
                    if stat.S_ISREG(info.st_mode) and info.st_mtime < cutoff:
                        self.discard(self.workspace.relative(path))
                except (OSError, ValueError):
                    # A concurrent upload or failed cleanup must not interrupt new uploads.
                    continue

    def discard(self, relative_path: str) -> str:
        """Remove a staged copy and empty staging directories; cleanup is idempotent."""
        target = self._staged(relative_path)
        if target.is_file():
            target.unlink()
        directory = target.parent
        while directory != self.workspace.root and directory.is_relative_to(self.root):
            try:
                directory.rmdir()
            except OSError:
                break
            directory = directory.parent
        return self.workspace.relative(target)

    def _check_size(self, size: int) -> None:
        if self.limit is not None and size > self.limit:
            raise ValueError(f"Upload exceeds the configured budget of {self.limit} bytes")

    @staticmethod
    def _target(target_dir: Path, name: str) -> Path:
        target_dir.mkdir(parents=True, exist_ok=True)
        directory = target_dir / uuid4().hex
        directory.mkdir()
        return directory / name

    def _report(self, target: Path, size: int) -> StagedFile:
        return StagedFile(path=self.workspace.relative(target), location=str(target), size=size)
