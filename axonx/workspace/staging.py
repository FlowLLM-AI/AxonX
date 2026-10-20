"""Stage uploaded files inside isolated workspace directories."""

from __future__ import annotations

import os
import tempfile
from uuid import uuid4
from collections.abc import AsyncIterator
from contextlib import suppress
from pathlib import Path

from ..constants import DEFAULT_TRANSFER_BUDGET_BYTES
from ..utils.fs import atomic_write
from ..utils.async_work import run_blocking
from .models import StagedFile
from .paths import COPY_DIR, WorkspacePaths


class StagedFiles:
    """Store each upload in an isolated directory until consumed or discarded."""

    def __init__(
        self,
        workspace_path: Path,
        copy_dir: str = COPY_DIR,
        transfer_budget_bytes: int = DEFAULT_TRANSFER_BUDGET_BYTES,
    ) -> None:
        if transfer_budget_bytes <= 0:
            raise ValueError("transfer_budget_bytes must be positive")
        self.paths = WorkspacePaths(workspace_path, copy_dir)
        self.transfer_budget_bytes = transfer_budget_bytes

    def file(self, relative_path: str) -> Path:
        """Resolve an existing staged file within the upload tree."""
        target = self.paths.staged(relative_path)
        if not target.is_file():
            raise ValueError("Staged file does not exist")
        return target

    def store(self, data: bytes, filename: str, directory: str | None = None) -> StagedFile:
        """Store uploaded bytes and report where they landed."""
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("Uploaded content must be bytes")
        self._check_size(len(data))
        return self._place(self.paths.copy_directory(directory), self.paths.copy_name(filename), data)

    async def store_stream(
        self,
        chunks: AsyncIterator[bytes],
        filename: str,
        directory: str | None = None,
        size: int | None = None,
    ) -> StagedFile:
        """Store an uploaded stream without holding the whole body in memory.

        Bytes land in a temporary file and are published only after the declared
        length and transfer budget have been checked.
        """
        if size is not None:
            if size < 0:
                raise ValueError("Declared upload size must not be negative")
            self._check_size(size)
        name = self.paths.copy_name(filename)
        target_dir = self.paths.copy_directory(directory)
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
                    # A declared length can lie, so the limit is enforced on arrival too.
                    self._check_size(written)
                    # Writing here would stall every other request for as long as the
                    # body takes to land.
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
                # A refused upload should not leave the copy directory behind either.
                with suppress(OSError):
                    target_dir.rmdir()

    def discard(self, relative_path: str) -> str:
        """Delete one staged copy and the directories that held it.

        A copy that a consumer already moved elsewhere is gone rather than missing,
        so an absent file is not an error.
        """
        target = self.paths.staged(relative_path)
        if target.is_file():
            target.unlink()
        directory = target.parent
        while directory != self.paths.root and directory.is_relative_to(self.paths.copy_root):
            try:
                directory.rmdir()
            except OSError:
                break
            directory = directory.parent
        return self.paths.relative(target)

    def _check_size(self, size: int) -> None:
        if size > self.transfer_budget_bytes:
            raise ValueError(f"Upload exceeds the configured budget of {self.transfer_budget_bytes} bytes")

    def _place(self, target_dir: Path, name: str, data: bytes) -> StagedFile:
        target = self._target(target_dir, name)
        try:
            atomic_write(target, lambda temporary: temporary.write_bytes(bytes(data)))
        except BaseException:
            target.parent.rmdir()
            raise
        return self._report(target, len(data))

    def _target(self, target_dir: Path, name: str) -> Path:
        """Reserve a unique upload directory; paths are confined by WorkspacePaths."""
        target_dir.mkdir(parents=True, exist_ok=True)
        directory = target_dir / uuid4().hex
        directory.mkdir()
        return directory / name

    def _report(self, target: Path, size: int) -> StagedFile:
        return StagedFile(path=self.paths.relative(target), location=str(target), size=size)
