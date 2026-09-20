"""Validate and atomically apply Task snapshot archives."""

from __future__ import annotations

import os
import shutil
import tarfile
import tempfile
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

from ...constants import MAX_UPLOAD_BYTES
from ...workspace.paths import WorkspacePaths
from ..storage.workspace import parse_task_directory, read_status
from .models import SyncTasksReport

MAX_SYNC_DELETIONS = 200
MAX_ARCHIVE_MEMBERS = 100_000
MAX_EXTRACT_RATIO = 100


class TaskArchiveApplier:
    """Apply complete Task snapshots with rollback on commit failure."""

    def __init__(self, workspace_path: Path) -> None:
        self.paths = WorkspacePaths(workspace_path)

    def apply(
        self,
        archive_path: Path | None,
        deletions: Sequence[str],
        archive_name: str | None = None,
    ) -> SyncTasksReport:
        removed = self._deletions(deletions)
        if archive_path is not None and archive_path.stat().st_size > MAX_UPLOAD_BYTES:
            raise ValueError(f"Sync archive exceeds {MAX_UPLOAD_BYTES} bytes")
        with tempfile.TemporaryDirectory(
            prefix=".axonx-sync-", dir=self.paths.root
        ) as temporary:
            staging = Path(temporary)
            extracted = staging / "incoming"
            replacements, files = self._extract(archive_path, extracted)
            overlap = replacements & set(removed)
            if overlap:
                raise ValueError(
                    f"Tasks cannot be replaced and deleted together: {', '.join(sorted(overlap))}"
                )
            deleted = self._commit(extracted, replacements, removed, staging / "backup")
        return SyncTasksReport(archive_name, sorted(replacements), deleted, files)

    def _extract(self, archive_path: Path | None, target: Path) -> tuple[set[str], int]:
        if archive_path is None:
            return set(), 0
        try:
            with tarfile.open(archive_path, "r:gz") as archive:
                members = archive.getmembers()
                self._check_bounds(members)
                tasks: set[str] = set()
                names: set[str] = set()
                for member in members:
                    validated = self._member(member, str(target))
                    canonical = PurePosixPath(validated.name).as_posix()
                    if validated.name != canonical:
                        raise ValueError(
                            f"Sync archive member is not canonical: {validated.name}"
                        )
                    if canonical in names:
                        raise ValueError(
                            f"Sync archive contains a duplicate member: {canonical}"
                        )
                    names.add(canonical)
                    tasks.add(self._task_of(canonical))
                target.mkdir()
                archive.extractall(target, members=members, filter=self._member)
                self._validate_snapshots(target, tasks)
                return tasks, len(members)
        except tarfile.TarError as exc:
            raise ValueError(f"Invalid sync archive: {exc}") from exc

    @staticmethod
    def _check_bounds(members: Sequence[tarfile.TarInfo]) -> None:
        if len(members) > MAX_ARCHIVE_MEMBERS:
            raise ValueError(f"Sync archive exceeds {MAX_ARCHIVE_MEMBERS} members")
        if (
            sum(member.size for member in members)
            > MAX_UPLOAD_BYTES * MAX_EXTRACT_RATIO
        ):
            raise ValueError("Sync archive expands beyond the configured limit")

    def _member(self, member: tarfile.TarInfo, destination: str) -> tarfile.TarInfo:
        if not member.isfile() or member.issym() or member.islnk():
            raise ValueError(
                f"Sync archives may contain only regular files: {member.name}"
            )
        self._task_of(member.name)
        validated = tarfile.data_filter(member, destination)
        if validated is None:
            raise ValueError(f"Sync archive member was rejected: {member.name}")
        return validated

    @staticmethod
    def _task_of(name: str) -> str:
        parts = PurePosixPath(name).parts
        if len(parts) < 3 or ".." in parts:
            raise ValueError(
                f"Sync archive member is not inside a task directory: {name}"
            )
        relative_path = "/".join(parts[:2])
        parse_task_directory(relative_path)
        return relative_path

    def _deletions(self, deletions: Sequence[str]) -> list[str]:
        if isinstance(deletions, (str, bytes)):
            raise TypeError("Sync deletions must be a sequence of task directories")
        unique = list(dict.fromkeys(deletions))
        if len(unique) > MAX_SYNC_DELETIONS:
            raise ValueError(f"At most {MAX_SYNC_DELETIONS} task deletions are allowed")
        for relative_path in unique:
            parse_task_directory(relative_path)
            self.paths.resolve_deletable(relative_path)
        return unique

    @staticmethod
    def _validate_snapshots(root: Path, tasks: set[str]) -> None:
        for relative_path in tasks:
            task_id = relative_path.split("/", 1)[1]
            status = read_status(root / relative_path, task_id)
            if status is None or not status.state.is_terminal:
                raise ValueError(
                    f"Sync archive Task is missing a terminal status: {relative_path}"
                )

    def _commit(
        self,
        extracted: Path,
        replacements: set[str],
        deletions: Sequence[str],
        backup_root: Path,
    ) -> list[str]:
        targets = sorted(replacements | set(deletions))
        backups: list[tuple[Path, Path]] = []
        installed: list[Path] = []
        deleted: list[str] = []
        try:
            for relative_path in targets:
                target = self.paths.resolve_deletable(relative_path)
                if not target.exists():
                    continue
                if target.is_symlink() or not target.is_dir():
                    raise ValueError(f"Task target is not a directory: {relative_path}")
                backup = backup_root / relative_path
                backup.parent.mkdir(parents=True, exist_ok=True)
                os.replace(target, backup)
                backups.append((target, backup))
                if relative_path in deletions:
                    deleted.append(relative_path)
            for relative_path in sorted(replacements):
                incoming = extracted / relative_path
                if not incoming.is_dir():
                    raise ValueError(
                        f"Sync archive has no files for task: {relative_path}"
                    )
                target = self.paths.resolve_deletable(relative_path)
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(incoming, target)
                installed.append(target)
        except BaseException:
            for target in reversed(installed):
                shutil.rmtree(target, ignore_errors=True)
            for target, backup in reversed(backups):
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(backup, target)
            raise
        return deleted
