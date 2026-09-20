"""Stage uploaded files inside the workspace under a content-addressed name."""

from __future__ import annotations

import asyncio
import hashlib
import os
import tempfile
from collections.abc import AsyncIterator
from contextlib import suppress
from pathlib import Path

from ..constants import MAX_UPLOAD_BYTES
from ..utils.fs import atomic_write, file_sha256
from .models import StagedFile
from .paths import COPY_DIR, WorkspacePaths


class StagedFiles:
    """Store uploaded files under a digest of their content.

    Naming the directory after the digest keeps repeated copies of identical content
    idempotent while a changed rebuild never overwrites an earlier one. The staging
    tree exists only to carry a copy to its consumer, so it is emptied again as soon
    as a copy is consumed or refused.
    """

    def __init__(
        self,
        workspace_path: Path,
        copy_dir: str = COPY_DIR,
        max_upload_bytes: int = MAX_UPLOAD_BYTES,
    ) -> None:
        if max_upload_bytes <= 0:
            raise ValueError("max_upload_bytes must be positive")
        self.paths = WorkspacePaths(workspace_path, copy_dir)
        self.max_upload_bytes = max_upload_bytes

    def file(self, relative_path: str) -> Path:
        """Resolve and verify an existing content-addressed staged file."""
        target = self.paths.staged(relative_path)
        if not target.is_file():
            raise ValueError("Staged file does not exist")
        expected = target.parent.name
        if (
            len(expected) != 64
            or any(character not in "0123456789abcdef" for character in expected)
            or file_sha256(target) != expected
        ):
            raise ValueError("Staged file content does not match its path")
        return target

    def store(
        self, data: bytes, filename: str, directory: str | None = None
    ) -> StagedFile:
        """Store uploaded bytes and report where they landed."""
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("Uploaded content must be bytes")
        self._check_size(len(data))
        return self._place(
            self.paths.copy_directory(directory), self.paths.copy_name(filename), data
        )

    async def store_stream(
        self,
        chunks: AsyncIterator[bytes],
        filename: str,
        directory: str | None = None,
        size: int | None = None,
    ) -> StagedFile:
        """Store an uploaded stream without holding the whole body in memory.

        The digest is only known once the last chunk lands, so the bytes wait in a
        temporary sibling and move into place after it is computed.
        """
        if size is not None:
            if size < 0:
                raise ValueError("Declared upload size must not be negative")
            self._check_size(size)
        name = self.paths.copy_name(filename)
        target_dir = self.paths.copy_directory(directory)
        existed = target_dir.is_dir()
        target_dir.mkdir(parents=True, exist_ok=True)

        digest = hashlib.sha256()
        written = 0
        descriptor, temporary = tempfile.mkstemp(
            dir=target_dir, prefix=f".{name}.", suffix=".tmp"
        )
        pending: Path | None = Path(temporary)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                async for chunk in chunks:
                    if not isinstance(chunk, (bytes, bytearray)):
                        raise TypeError("Uploaded content must be bytes")
                    written += len(chunk)
                    # A declared length can lie, so the limit is enforced on arrival too.
                    self._check_size(written)
                    digest.update(chunk)
                    # Writing here would stall every other request for as long as the
                    # body takes to land.
                    await asyncio.to_thread(handle.write, chunk)
            if size is not None and written != size:
                raise ValueError(
                    f"Uploaded content size {written} does not match declared size {size}"
                )
            hexdigest = digest.hexdigest()
            target = self._target(target_dir, name, hexdigest)
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(pending, target)
                pending = None
            return self._report(target, hexdigest, written)
        finally:
            if pending is not None:
                pending.unlink(missing_ok=True)
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
        while directory != self.paths.root and directory.is_relative_to(
            self.paths.copy_root
        ):
            try:
                directory.rmdir()
            except OSError:
                break
            directory = directory.parent
        return self.paths.relative(target)

    def _check_size(self, size: int) -> None:
        if size > self.max_upload_bytes:
            raise ValueError(
                f"Upload exceeds the configured limit of {self.max_upload_bytes} bytes"
            )

    def _place(self, target_dir: Path, name: str, data: bytes) -> StagedFile:
        digest = hashlib.sha256(data).hexdigest()
        target = self._target(target_dir, name, digest)
        if not target.exists():
            atomic_write(target, lambda temporary: temporary.write_bytes(bytes(data)))
        return self._report(target, digest, len(data))

    def _target(self, target_dir: Path, name: str, digest: str) -> Path:
        """Return the content-addressed destination, refusing a tampered copy."""
        digest_dir = target_dir / digest
        if digest_dir.is_symlink():
            raise FileExistsError("Workspace copy digest directory cannot be a symlink")
        digest_dir = digest_dir.resolve()
        if not digest_dir.is_relative_to(self.paths.copy_root):
            raise FileExistsError("Workspace copy destination escaped its staging root")
        target = digest_dir / name
        if target.is_symlink():
            raise FileExistsError(f"Workspace copy cannot be a symlink: {target.name}")
        if target.exists() and (not target.is_file() or file_sha256(target) != digest):
            raise FileExistsError(
                f"Workspace copy already holds different content: {target.name}"
            )
        return target

    def _report(self, target: Path, digest: str, size: int) -> StagedFile:
        """Return the copy outcome in workspace-relative and absolute form."""
        return StagedFile(
            path=self.paths.relative(target),
            location=str(target),
            sha256=digest,
            size=size,
        )
