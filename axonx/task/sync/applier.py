"""Validate and atomically apply display-replica archives."""

from __future__ import annotations

import os
import shutil
import tarfile
import tempfile
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

from ...constants import DEFAULT_TRANSFER_BUDGET_BYTES
from ...workspace.paths import WorkspacePaths
from ...utils.fs import file_sha256, snapshot_file
from ..storage.workspace import (
    parse_task_directory,
    read_task_metadata,
    task_directory,
    read_entry,
)
from .index import verify_replica
from ..schemas.lifecycle import current_children
from .models import SyncTasksReport

MAX_SYNC_DELETIONS = 200
MAX_ARCHIVE_MEMBERS = 100_000


class TaskArchiveApplier:
    """Apply verified display replicas with rollback on commit failure."""

    def __init__(
        self,
        workspace_path: Path,
        transfer_budget_bytes: int = DEFAULT_TRANSFER_BUDGET_BYTES,
    ) -> None:
        self.paths = WorkspacePaths(workspace_path)
        self.transfer_budget_bytes = transfer_budget_bytes

    def apply(
        self,
        archive_path: Path | None,
        deletions: Sequence[str],
        archive_name: str | None = None,
    ) -> SyncTasksReport:
        removed = self._deletions(deletions)
        if archive_path is not None and archive_path.stat().st_size > self.transfer_budget_bytes:
            raise ValueError(f"Sync archive exceeds {self.transfer_budget_bytes} bytes")
        with tempfile.TemporaryDirectory(prefix=".axonx-sync-", dir=self.paths.root) as temporary:
            staging = Path(temporary)
            extracted = staging / "incoming"
            replacements, files = self._extract(archive_path, extracted)
            overlap = replacements & set(removed)
            if overlap:
                raise ValueError(f"Tasks cannot be replaced and deleted together: {', '.join(sorted(overlap))}")
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
                        raise ValueError(f"Sync archive member is not canonical: {validated.name}")
                    if canonical in names:
                        raise ValueError(f"Sync archive contains a duplicate member: {canonical}")
                    names.add(canonical)
                    tasks.add(self._task_of(canonical))
                target.mkdir()
                archive.extractall(target, members=members, filter=self._member)
                self._hydrate(target, tasks)
                self._validate_snapshots(target, tasks)
                return tasks, len(members)
        except tarfile.TarError as exc:
            raise ValueError(f"Invalid sync archive: {exc}") from exc

    def _check_bounds(self, members: Sequence[tarfile.TarInfo]) -> None:
        if len(members) > MAX_ARCHIVE_MEMBERS:
            raise ValueError(f"Sync archive exceeds {MAX_ARCHIVE_MEMBERS} members")
        if 10240 + sum(512 + ((member.size + 511) // 512) * 512 for member in members) > self.transfer_budget_bytes:
            raise ValueError("Sync archive expands beyond the configured limit")

    def _member(self, member: tarfile.TarInfo, destination: str) -> tarfile.TarInfo:
        if not member.isfile() or member.issym() or member.islnk():
            raise ValueError(f"Sync archives may contain only regular files: {member.name}")
        self._task_of(member.name)
        validated = tarfile.data_filter(member, destination)
        if validated is None:
            raise ValueError(f"Sync archive member was rejected: {member.name}")
        return validated

    @staticmethod
    def _task_of(name: str) -> str:
        parts = PurePosixPath(name).parts
        if len(parts) < 3 or ".." in parts:
            raise ValueError(f"Sync archive member is not inside a task directory: {name}")
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

    def _hydrate(self, root: Path, tasks: set[str]) -> None:
        """Reuse only explicitly checksummed files from the same existing Run."""
        expanded = 10240 + sum(512 + ((p.stat().st_size + 511) // 512) * 512 for p in root.rglob("*") if p.is_file())
        for relative_path in tasks:
            directory = root / relative_path
            task_id = relative_path.split("/", 1)[1]
            status = read_task_metadata(directory, task_id)
            if status is None or status.replica is None or status.replica.snapshot is None:
                continue
            previous = read_task_metadata(self.paths.root / relative_path, task_id)
            for name, record in status.replica.files.items():
                path = Path(name)
                if path.is_absolute() or ".." in path.parts or path.as_posix() != name:
                    raise ValueError(f"Invalid replica path: {name}")
                target = directory / name
                if target.is_file():
                    continue
                expanded += 512 + ((record.size + 511) // 512) * 512
                if expanded > self.transfer_budget_bytes:
                    raise ValueError("Hydrated replica exceeds the transfer budget")
                old = previous.replica if previous is not None and previous.run_id == status.run_id else None
                if old is None:
                    raise ValueError(f"Missing replica delta base: {task_id}/{name}")
                source = self.paths.root / relative_path / name
                if old.files.get(name) != record or any(p.is_symlink() for p in (source, *source.parents)):
                    raise ValueError(f"Replica delta base differs: {task_id}/{name}")
                if source.stat().st_size != record.size or file_sha256(source) != record.sha256:
                    raise ValueError(f"Replica delta base is corrupt: {task_id}/{name}")
                target.parent.mkdir(parents=True, exist_ok=True)
                snapshot_file(source, target)

    @staticmethod
    def _validate_snapshots(root: Path, tasks: set[str]) -> None:
        for relative_path in tasks:
            task_id = relative_path.split("/", 1)[1]
            status = read_task_metadata(root / relative_path, task_id)
            if status is None or status.replica is None:
                raise ValueError(f"Sync archive Task is missing a display replica status: {relative_path}")
            snapshot = status.replica.snapshot
            if snapshot is not None:
                if task_directory(snapshot.root_task_id) not in tasks:
                    raise ValueError("Live snapshot must include its parent Task")
                parent = read_entry(root, snapshot.root_task_id)
                if (
                    parent is None
                    or parent.replica is None
                    or parent.run_id != snapshot.root_run_id
                    or parent.replica.snapshot != snapshot
                ):
                    raise ValueError("Live snapshot parent identity differs")
                for child in current_children(status):
                    if child.task_id is None:
                        continue
                    linked = read_entry(root, child.task_id)
                    if (
                        linked is None
                        or linked.run_id != child.run_id
                        or linked.replica is None
                        or linked.replica.snapshot != snapshot
                    ):
                        raise ValueError("Live snapshot child identity differs")
            verify_replica(root, task_id)

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
                status = read_task_metadata(target, relative_path.split("/", 1)[1], strict_io=True)
                incoming = (
                    read_task_metadata(extracted / relative_path, relative_path.split("/", 1)[1])
                    if relative_path in replacements
                    else None
                )
                old = status.replica.snapshot if status is not None and status.replica is not None else None
                new = incoming.replica.snapshot if incoming is not None and incoming.replica is not None else None
                if old is not None and incoming is not None:
                    if (
                        new is None
                        or new.source_id != old.source_id
                        or new.root_task_id != old.root_task_id
                        or new.revision <= old.revision
                    ):
                        raise ValueError(f"Stale or conflicting live snapshot: {relative_path}")
                    if status.run_id == incoming.run_id and status.state.is_terminal and not incoming.state.is_terminal:
                        raise ValueError(f"Cannot regress a terminal Run: {relative_path}")
                if status is not None and not status.state.is_terminal and (old is None or new is None):
                    raise ValueError(f"Cannot overwrite active Task: {relative_path}")
                backup = backup_root / relative_path
                backup.parent.mkdir(parents=True, exist_ok=True)
                os.replace(target, backup)
                backups.append((target, backup))
                if relative_path in deletions:
                    deleted.append(relative_path)
            for relative_path in sorted(replacements):
                incoming = extracted / relative_path
                if not incoming.is_dir():
                    raise ValueError(f"Sync archive has no files for task: {relative_path}")
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
