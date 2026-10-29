"""Validate and atomically apply display-replica archives."""

from __future__ import annotations

import os
import shutil
import tarfile
import tempfile
from collections.abc import Sequence
from pathlib import Path, PurePosixPath

from ....task.storage.files import snapshot_file
from ....task.storage.workspace import (
    parse_task_directory,
    read_entry,
    read_task_metadata,
    resolve_relative_path,
    scan_entries,
    task_directory,
    task_id_from_path,
)
from ....utils.logging import get_logger
from .artifacts import artifact_path, verify_replica
from .models import TAR_PADDING_BYTES, SyncTasksReport, archived_bytes

MAX_SYNC_DELETIONS = 200
MAX_ARCHIVE_MEMBERS = 100_000


class TaskArchiveApplier:
    """Apply verified display replicas with rollback on commit failure."""

    def __init__(
        self,
        workspace_path: Path,
        transfer_budget_bytes: int,
    ) -> None:
        if (
            isinstance(transfer_budget_bytes, bool)
            or not isinstance(transfer_budget_bytes, int)
            or transfer_budget_bytes <= 0
        ):
            raise ValueError("transfer_budget_bytes must be a positive integer")
        self.root = Path(workspace_path).expanduser().resolve()
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
        temporary_root = resolve_relative_path(self.root, "tmp/sync")
        temporary_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="receive-", dir=temporary_root) as temporary:
            staging = Path(temporary)
            extracted = staging / "incoming"
            replacements, files = self._extract(archive_path, extracted)
            overlap = replacements & set(removed)
            if overlap:
                raise ValueError(f"Tasks cannot be replaced and deleted together: {', '.join(sorted(overlap))}")
            snapshots = {
                (status.replica.snapshot.source_id, status.replica.snapshot.root_task_id)
                for relative in replacements
                if (status := read_task_metadata(extracted / relative, relative.rsplit("/", 1)[1])) is not None
                and status.replica is not None
                and status.replica.snapshot is not None
            }
            obsolete = {
                task_directory(identity)
                for identity, status in scan_entries(self.root).items()
                if status.replica is not None
                and status.replica.snapshot is not None
                and (status.replica.snapshot.source_id, status.replica.snapshot.root_task_id) in snapshots
                and task_directory(identity) not in replacements
            }
            deleted = self._commit(extracted, replacements, sorted(set(removed) | obsolete), staging / "backup")
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
                _validate_snapshots(target, tasks)
                return tasks, len(members)
        except tarfile.TarError as exc:
            raise ValueError(f"Invalid sync archive: {exc}") from exc

    def _check_bounds(self, members: Sequence[tarfile.TarInfo]) -> None:
        if len(members) > MAX_ARCHIVE_MEMBERS:
            raise ValueError(f"Sync archive exceeds {MAX_ARCHIVE_MEMBERS} members")
        if TAR_PADDING_BYTES + sum(archived_bytes(member.size) for member in members) > self.transfer_budget_bytes:
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
        identity = task_id_from_path(Path(), name)
        if identity is None or ".." in PurePosixPath(name).parts or name == task_directory(identity):
            raise ValueError(f"Sync archive member is not inside a task directory: {name}")
        return task_directory(identity)

    def _deletions(self, deletions: Sequence[str]) -> list[str]:
        if isinstance(deletions, (str, bytes)):
            raise TypeError("Sync deletions must be a sequence of task directories")
        unique = list(dict.fromkeys(deletions))
        if len(unique) > MAX_SYNC_DELETIONS:
            raise ValueError(f"At most {MAX_SYNC_DELETIONS} task deletions are allowed")
        for relative_path in unique:
            parse_task_directory(relative_path)
            resolve_relative_path(self.root, relative_path)
        return unique

    def _hydrate(self, root: Path, tasks: set[str]) -> None:
        """Reuse only explicitly versioned files from the same current Task."""
        expanded = TAR_PADDING_BYTES + sum(archived_bytes(p.stat().st_size) for p in root.rglob("*") if p.is_file())
        for relative_path in tasks:
            directory = root / relative_path
            task_id = relative_path.rsplit("/", 1)[1]
            status = read_task_metadata(directory, task_id)
            if status is None or status.replica is None or status.replica.snapshot is None:
                continue
            previous = read_task_metadata(self.root / relative_path, task_id)
            for name, record in status.replica.files.items():
                target = artifact_path(directory, name)
                if target.is_file():
                    continue
                expanded += archived_bytes(record.size)
                if expanded > self.transfer_budget_bytes:
                    raise ValueError("Hydrated replica exceeds the transfer budget")
                old = previous.replica if previous is not None and previous.started_at == status.started_at else None
                if old is None:
                    raise ValueError(f"Missing replica delta base: {task_id}/{name}")
                source = artifact_path(self.root / relative_path, name)
                if old.files.get(name) != record:
                    raise ValueError(f"Replica delta base differs: {task_id}/{name}")
                if source.stat().st_size != record.size:
                    raise ValueError(f"Replica delta base is corrupt: {task_id}/{name}")
                target.parent.mkdir(parents=True, exist_ok=True)
                snapshot_file(source, target)

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
                target = resolve_relative_path(self.root, relative_path)
                if not target.exists():
                    continue
                if target.is_symlink() or not target.is_dir():
                    raise ValueError(f"Task target is not a directory: {relative_path}")
                status = read_task_metadata(target, relative_path.rsplit("/", 1)[1], strict_io=True)
                incoming = (
                    read_task_metadata(extracted / relative_path, relative_path.rsplit("/", 1)[1])
                    if relative_path in replacements
                    else None
                )
                old = status.replica.snapshot if status is not None and status.replica is not None else None
                new = incoming.replica.snapshot if incoming is not None and incoming.replica is not None else None
                if old is not None and incoming is not None:
                    # Completed shared children can later sync independently.
                    # A new live parent may also reference the same child execution.
                    if new is None:
                        conflict = not (
                            status.started_at == incoming.started_at
                            and status.state.is_terminal
                            and incoming.state.is_terminal
                        )
                    else:
                        conflict = new.source_id != old.source_id or new.revision <= old.revision
                    if conflict:
                        raise ValueError(f"Stale or conflicting Task snapshot: {relative_path}")
                if status is not None and status.replica is not None and incoming is not None:
                    if (
                        status.started_at == incoming.started_at
                        and status.state.is_terminal
                        and not incoming.state.is_terminal
                    ):
                        raise ValueError(f"Cannot regress a terminal Task: {relative_path}")
                if (
                    status is not None
                    and not status.state.is_terminal
                    and (old is None or new is None)
                    and not (relative_path in deletions and status.replica is not None)
                ):
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
                target = resolve_relative_path(self.root, relative_path)
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


def _validate_snapshots(root: Path, tasks: set[str]) -> None:
    for relative_path in tasks:
        task_id = relative_path.rsplit("/", 1)[1]
        status = read_task_metadata(root / relative_path, task_id)
        if status is None or status.replica is None:
            raise ValueError(f"Sync archive Task is missing a display replica status: {relative_path}")
        snapshot = status.replica.snapshot
        if snapshot is not None:
            if task_directory(snapshot.root_task_id) not in tasks:
                raise ValueError("Task snapshot must include its parent Task")
            parent = read_entry(root, snapshot.root_task_id)
            if (
                parent is None
                or parent.replica is None
                or parent.started_at != snapshot.root_started_at
                or parent.replica.snapshot != snapshot
            ):
                raise ValueError("Task snapshot parent identity differs")
            for child in status.current_children():
                if child.child_task_id is None or child.started_at is None:
                    continue
                linked = read_entry(root, child.child_task_id)
                if (
                    linked is None
                    or linked.started_at != child.started_at
                    or linked.replica is None
                    or linked.replica.snapshot != snapshot
                ):
                    raise ValueError("Task snapshot child identity differs")
        verify_replica(root, task_id, metadata=status)


def snapshot_index(root: Path, root_task_ids: frozenset[str] = frozenset()) -> dict:
    """Index complete, verified groups so a missing member triggers reconciliation."""
    groups = {}
    for identity, metadata in scan_entries(root).items():
        replica = metadata.replica
        if replica is None:
            continue
        owner = replica.snapshot.root_task_id if replica.snapshot else identity
        if root_task_ids and owner not in root_task_ids:
            continue
        groups.setdefault(owner, {})[identity] = metadata
    result = {}
    for owner, group in groups.items():
        try:
            _validate_snapshots(root, {task_directory(identity) for identity in group})
        except (OSError, ValueError) as exc:
            get_logger("task-sync-index").warning(f"Skipping invalid display group {owner}: {exc}")
            continue
        result.update(
            {
                identity: {"started_at": metadata.started_at.isoformat(), **metadata.replica.model_dump(mode="json")}
                for identity, metadata in group.items()
            }
        )
    return result
